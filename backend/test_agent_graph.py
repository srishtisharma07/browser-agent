"""
test_agent_graph.py — Verification test suite for Bounded Autonomous Agent Loop.

Run from backend/ directory:

    .venv\\Scripts\\python test_agent_graph.py

Tests verified:
1. Graph construction and compilation via LangGraph.
2. Response path (START -> decide -> execute -> verify -> END).
3. Tool-call path (open_url through ToolRegistry boundary).
4. Tool failure handling (verification status = action_failed, task not marked COMPLETED).
5. Unknown tool rejection (delete_everything rejected safely).
6. AgentState preservation across graph execution.
7. Dependency injection works without global singletons or API keys.
8. Safety verification (no eval, exec, shell commands, or direct Playwright calls).
9. Multi-cycle sequential execution (open_url -> get_page_text -> respond).
10. Max cycles termination limit enforcement (stops at max_cycles=2).
11. Tool success != Task completion (tool success continues loop).
12. Consecutive duplicate action loop protection (stops after 3 identical actions).
13. Explicit STOPPED task status termination.
14. Invalid max_cycles validation (rejects 0 or negative numbers).
"""

import sys
import logging
import inspect
from typing import List
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from app.agent.state import AgentState, Constraint, DiscoveredItem, RejectedItem, TaskStatus
from app.agent.tools import ToolRegistry
from app.agent.decision import AgentDecisionEngine
from app.agent.graph import create_agent_graph, run_agent_graph
from app.llm.provider import LLMProvider, LLMResponse, LLMToolCall
from app.browser.manager import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


class MockLLMProvider(LLMProvider):
    """Fake LLM Provider for deterministic single-response testing."""

    def __init__(self, response: LLMResponse):
        self.response = response

    def generate(self, prompt, tools=None, system_instruction=None):
        return self.response


class MockSequentialLLMProvider(LLMProvider):
    """Fake LLM Provider returning a sequence of responses across multiple graph cycles."""

    def __init__(self, responses: List[LLMResponse]):
        self.responses = responses
        self.call_count = 0

    def generate(self, prompt, tools=None, system_instruction=None):
        if self.call_count < len(self.responses):
            res = self.responses[self.call_count]
        else:
            res = self.responses[-1]
        self.call_count += 1
        return res


def create_sample_state() -> AgentState:
    """Helper to construct a populated AgentState."""
    return AgentState(
        task_id="graph-task-001",
        user_goal="Search for software engineer jobs",
        extracted_constraints=[
            Constraint(name="location", value="Remote"),
        ],
        current_plan=["Navigate to job board"],
        completed_steps=[],
        current_step=None,
        discovered_items=[
            DiscoveredItem(title="Backend Dev", url="https://example.com/job1")
        ],
        rejected_items=[
            RejectedItem(title="Intern", url="https://example.com/job2", reason="Not qualified")
        ],
        task_status=TaskStatus.RUNNING,
    )


def run_agent_graph_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — Bounded Autonomous Loop Test Suite")
    log.info("=" * 65)

    try:
        mock_browser_mgr = MagicMock(spec=BrowserManager)

        # ---------------------------------------------------------------------
        # TEST 1: Graph Construction & Compilation
        # ---------------------------------------------------------------------
        log.info("STEP 1 · Testing LangGraph construction and compilation…")
        registry1 = ToolRegistry(mock_browser_mgr)
        provider1 = MockLLMProvider(LLMResponse(text="Hello"))
        engine1 = AgentDecisionEngine(registry1, provider1)

        graph1 = create_agent_graph(decision_engine=engine1)
        if graph1 is None:
            log.error("❌ FAILED: create_agent_graph returned None")
            all_passed = False
        else:
            log.info("✔ LangGraph constructed and compiled successfully!")

        # ---------------------------------------------------------------------
        # TEST 2: Single-Cycle Response Path
        # ---------------------------------------------------------------------
        log.info("\nSTEP 2 · Testing Response Path (Direct Text Response)…")
        state2 = create_sample_state()
        registry2 = ToolRegistry(mock_browser_mgr)
        provider2 = MockLLMProvider(LLMResponse(text="Tasks complete, no browser action required."))

        graph2 = create_agent_graph(tool_registry=registry2, llm_provider=provider2)
        res2 = run_agent_graph(graph2, state2)

        if res2.decision.action != "respond":
            log.error("❌ FAILED: Expected decision action 'respond', got '%s'", res2.decision.action)
            all_passed = False
        elif res2.verification_status != "response_success":
            log.error("❌ FAILED: Expected verification_status 'response_success', got '%s'", res2.verification_status)
            all_passed = False
        elif res2.stop_reason != "completed_response":
            log.error("❌ FAILED: Expected stop_reason 'completed_response', got '%s'", res2.stop_reason)
            all_passed = False
        elif mock_browser_mgr.method_calls:
            log.error("❌ FAILED: Browser manager was called during text response path")
            all_passed = False
        else:
            log.info("✔ Single-Cycle Response Path PASSED!")

        # ---------------------------------------------------------------------
        # TEST 3: Tool-Call Path
        # ---------------------------------------------------------------------
        log.info("\nSTEP 3 · Testing Tool-Call Path (open_url execution)…")
        state3 = create_sample_state()
        mock_browser_mgr.reset_mock()
        mock_browser_mgr.open_url.return_value = {
            "success": True,
            "url": "https://example.com/jobs",
            "error": None
        }
        registry3 = ToolRegistry(mock_browser_mgr)
        # Sequence: open_url -> respond
        provider3 = MockSequentialLLMProvider([
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://example.com/jobs"})]),
            LLMResponse(text="Loaded jobs page successfully.")
        ])

        graph3 = create_agent_graph(tool_registry=registry3, llm_provider=provider3)
        res3 = run_agent_graph(graph3, state3)

        if res3.cycle_count != 2:
            log.error("❌ FAILED: Expected cycle_count 2, got %d", res3.cycle_count)
            all_passed = False
        elif res3.verification_status != "response_success":
            log.error("❌ FAILED: Expected final verification_status 'response_success', got '%s'", res3.verification_status)
            all_passed = False
        elif not mock_browser_mgr.open_url.called:
            log.error("❌ FAILED: BrowserManager.open_url was not called")
            all_passed = False
        else:
            log.info("✔ Tool-Call Path PASSED!")

        # ---------------------------------------------------------------------
        # TEST 4: Tool Failure Handling
        # ---------------------------------------------------------------------
        log.info("\nSTEP 4 · Testing Tool Failure Handling…")
        state4 = create_sample_state()
        mock_browser_mgr.reset_mock()
        mock_browser_mgr.click.return_value = {
            "success": False,
            "error": "Timeout 30000ms waiting for element #submit",
            "url": "https://example.com"
        }
        registry4 = ToolRegistry(mock_browser_mgr)
        provider4 = MockLLMProvider(LLMResponse(
            tool_calls=[LLMToolCall(name="click", arguments={"selector": "#submit"})]
        ))

        graph4 = create_agent_graph(tool_registry=registry4, llm_provider=provider4)
        res4 = run_agent_graph(graph4, state4, max_cycles=1)

        if res4.verification_status != "action_failed":
            log.error("❌ FAILED: Expected verification_status 'action_failed', got '%s'", res4.verification_status)
            all_passed = False
        elif res4.final_state.task_status == TaskStatus.COMPLETED:
            log.error("❌ FAILED: Task status was incorrectly set to COMPLETED after tool failure")
            all_passed = False
        else:
            log.info("✔ Tool Failure Handling PASSED!")

        # ---------------------------------------------------------------------
        # TEST 5: Unknown Tool Rejection
        # ---------------------------------------------------------------------
        log.info("\nSTEP 5 · Testing Unknown Tool Rejection…")
        state5 = create_sample_state()
        mock_browser_mgr.reset_mock()
        registry5 = ToolRegistry(mock_browser_mgr)
        provider5 = MockLLMProvider(LLMResponse(
            tool_calls=[LLMToolCall(name="delete_everything", arguments={})]
        ))

        graph5 = create_agent_graph(tool_registry=registry5, llm_provider=provider5)
        res5 = run_agent_graph(graph5, state5)

        if res5.decision.action != "error":
            log.error("❌ FAILED: Unknown tool was not rejected with action 'error'")
            all_passed = False
        elif res5.stop_reason != "execution_error":
            log.error("❌ FAILED: Expected stop_reason 'execution_error', got '%s'", res5.stop_reason)
            all_passed = False
        elif mock_browser_mgr.method_calls:
            log.error("❌ FAILED: Browser action executed for unknown tool")
            all_passed = False
        else:
            log.info("✔ Unknown Tool Rejection PASSED!")

        # ---------------------------------------------------------------------
        # TEST 6: AgentState Preservation
        # ---------------------------------------------------------------------
        log.info("\nSTEP 6 · Testing AgentState Preservation…")
        state6 = create_sample_state()
        registry6 = ToolRegistry(mock_browser_mgr)
        provider6 = MockLLMProvider(LLMResponse(text="Preservation check."))

        graph6 = create_agent_graph(tool_registry=registry6, llm_provider=provider6)
        res6 = run_agent_graph(graph6, state6)

        st = res6.final_state
        if st.task_id != "graph-task-001":
            log.error("❌ FAILED: task_id mutated")
            all_passed = False
        elif st.user_goal != "Search for software engineer jobs":
            log.error("❌ FAILED: user_goal mutated")
            all_passed = False
        elif len(st.extracted_constraints) != 1 or st.extracted_constraints[0].value != "Remote":
            log.error("❌ FAILED: extracted_constraints mutated")
            all_passed = False
        elif len(st.discovered_items) != 1 or st.discovered_items[0].title != "Backend Dev":
            log.error("❌ FAILED: discovered_items mutated")
            all_passed = False
        elif len(st.rejected_items) != 1 or st.rejected_items[0].title != "Intern":
            log.error("❌ FAILED: rejected_items mutated")
            all_passed = False
        else:
            log.info("✔ AgentState Preservation PASSED!")

        # ---------------------------------------------------------------------
        # TEST 7: Dependency Injection
        # ---------------------------------------------------------------------
        log.info("\nSTEP 7 · Testing Dependency Injection…")
        try:
            create_agent_graph()
            log.error("❌ FAILED: create_agent_graph accepted empty dependencies")
            all_passed = False
        except ValueError:
            log.info("✔ Rejection of missing dependencies PASSED!")

        # ---------------------------------------------------------------------
        # TEST 8: Safety Verification
        # ---------------------------------------------------------------------
        log.info("\nSTEP 8 · Testing Safety Boundaries…")
        from app.agent import graph as graph_module
        graph_code = inspect.getsource(graph_module)

        if "eval(" in graph_code or "exec(" in graph_code or "__import__" in graph_code:
            log.error("❌ FAILED: Dynamic code execution function found in graph module")
            all_passed = False
        elif "playwright" in graph_code.lower() or "page." in graph_code.lower():
            log.error("❌ FAILED: Direct Playwright access found in graph module")
            all_passed = False
        else:
            log.info("✔ Safety Boundaries PASSED!")

        # ---------------------------------------------------------------------
        # TEST 9: Multi-Cycle Sequential Execution
        # ---------------------------------------------------------------------
        log.info("\nSTEP 9 · Testing Multi-Cycle Sequential Execution (3 turns)…")
        state9 = create_sample_state()
        mock_browser_mgr.reset_mock()
        mock_browser_mgr.open_url.return_value = {"success": True, "url": "https://example.com"}
        mock_browser_mgr.get_page_text.return_value = {"success": True, "text": "Page text content"}
        registry9 = ToolRegistry(mock_browser_mgr)

        # Sequence: open_url -> get_page_text -> respond
        seq_provider = MockSequentialLLMProvider([
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://example.com"})]),
            LLMResponse(tool_calls=[LLMToolCall(name="get_page_text", arguments={"max_length": 500})]),
            LLMResponse(text="Found content: Page text content.")
        ])

        graph9 = create_agent_graph(tool_registry=registry9, llm_provider=seq_provider, max_cycles=5)
        res9 = run_agent_graph(graph9, state9, max_cycles=5)

        if res9.cycle_count != 3:
            log.error("❌ FAILED: Expected 3 cycles, got %d", res9.cycle_count)
            all_passed = False
        elif res9.stop_reason != "completed_response":
            log.error("❌ FAILED: Expected stop_reason 'completed_response', got '%s'", res9.stop_reason)
            all_passed = False
        elif len(res9.final_state.observations) != 3:
            log.error("❌ FAILED: Expected 3 accumulated observations in state, got %d", len(res9.final_state.observations))
            all_passed = False
        else:
            log.info("✔ Multi-Cycle Sequential Execution PASSED!")

        # ---------------------------------------------------------------------
        # TEST 10: Max Cycles Termination Limit
        # ---------------------------------------------------------------------
        log.info("\nSTEP 10 · Testing Max Cycles Termination Limit (max_cycles=2)…")
        state10 = create_sample_state()
        mock_browser_mgr.reset_mock()
        mock_browser_mgr.scroll.return_value = {"success": True, "url": "https://example.com"}
        registry10 = ToolRegistry(mock_browser_mgr)

        # Provider continuously returns scroll actions
        endless_provider = MockLLMProvider(LLMResponse(
            tool_calls=[LLMToolCall(name="scroll", arguments={"direction": "down", "amount": 100})]
        ))

        graph10 = create_agent_graph(tool_registry=registry10, llm_provider=endless_provider, max_cycles=2)
        res10 = run_agent_graph(graph10, state10, max_cycles=2)

        if res10.cycle_count != 2:
            log.error("❌ FAILED: Expected cycle_count 2, got %d", res10.cycle_count)
            all_passed = False
        elif res10.stop_reason != "max_cycles_reached":
            log.error("❌ FAILED: Expected stop_reason 'max_cycles_reached', got '%s'", res10.stop_reason)
            all_passed = False
        elif res10.final_state.task_status == TaskStatus.COMPLETED:
            log.error("❌ FAILED: Max cycles limit incorrectly marked task COMPLETED")
            all_passed = False
        else:
            log.info("✔ Max Cycles Termination Limit PASSED!")

        # ---------------------------------------------------------------------
        # TEST 11: Consecutive Duplicate Action Protection
        # ---------------------------------------------------------------------
        log.info("\nSTEP 11 · Testing Consecutive Duplicate Action Protection…")
        state11 = create_sample_state()
        mock_browser_mgr.reset_mock()
        mock_browser_mgr.open_url.return_value = {"success": True, "url": "https://example.com"}
        registry11 = ToolRegistry(mock_browser_mgr)

        repeat_provider = MockLLMProvider(LLMResponse(
            tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://example.com"})]
        ))

        graph11 = create_agent_graph(tool_registry=registry11, llm_provider=repeat_provider, max_cycles=10)
        res11 = run_agent_graph(graph11, state11, max_cycles=10)

        if res11.cycle_count != 3:
            log.error("❌ FAILED: Expected loop protection to stop at cycle 3, got %d", res11.cycle_count)
            all_passed = False
        elif res11.stop_reason != "consecutive_duplicate_action":
            log.error("❌ FAILED: Expected stop_reason 'consecutive_duplicate_action', got '%s'", res11.stop_reason)
            all_passed = False
        elif not any("Loop protection triggered" in err for err in res11.final_state.errors):
            log.error("❌ FAILED: Loop protection error was not added to state.errors")
            all_passed = False
        else:
            log.info("✔ Consecutive Duplicate Action Protection PASSED!")

        # ---------------------------------------------------------------------
        # TEST 12: Explicit STOPPED Task Status Termination
        # ---------------------------------------------------------------------
        log.info("\nSTEP 12 · Testing Explicit STOPPED Task Status Termination…")
        state12 = create_sample_state()
        state12.task_status = TaskStatus.STOPPED
        registry12 = ToolRegistry(mock_browser_mgr)
        provider12 = MockLLMProvider(LLMResponse(
            tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://example.com"})]
        ))

        graph12 = create_agent_graph(tool_registry=registry12, llm_provider=provider12)
        res12 = run_agent_graph(graph12, state12)

        if res12.stop_reason != "task_stopped":
            log.error("❌ FAILED: Expected stop_reason 'task_stopped', got '%s'", res12.stop_reason)
            all_passed = False
        elif res12.cycle_count != 0:
            log.error("❌ FAILED: Expected 0 cycles executed when status is STOPPED, got %d", res12.cycle_count)
            all_passed = False
        else:
            log.info("✔ Explicit STOPPED Task Status Termination PASSED!")

        # ---------------------------------------------------------------------
        # TEST 13: Invalid max_cycles Validation
        # ---------------------------------------------------------------------
        log.info("\nSTEP 13 · Testing Invalid max_cycles Validation…")
        try:
            create_agent_graph(tool_registry=registry1, llm_provider=provider1, max_cycles=0)
            log.error("❌ FAILED: Accepted max_cycles=0")
            all_passed = False
        except ValueError:
            log.info("✔ Accepted max_cycles validation rejection for 0.")

        try:
            run_agent_graph(graph1, state2, max_cycles=-5)
            log.error("❌ FAILED: Accepted max_cycles=-5")
            all_passed = False
        except ValueError:
            log.info("✔ Accepted max_cycles validation rejection for negative number.")

    except Exception as exc:
        log.error("❌ Test suite crashed: %s", exc, exc_info=True)
        all_passed = False

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL AGENT GRAPH LOOP TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_agent_graph_tests()
    sys.exit(0 if success else 1)
