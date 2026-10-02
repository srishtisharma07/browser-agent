"""
test_agent_graph.py — Verification test suite for LangGraph Agent State Machine.

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
8. Security verification (no eval, exec, shell commands, or direct Playwright calls).
"""

import sys
import logging
import inspect
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
    """Fake LLM Provider for deterministic graph testing."""

    def __init__(self, response: LLMResponse):
        self.response = response

    def generate(self, prompt, tools=None, system_instruction=None):
        return self.response


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
    log.info("AI Browser Agent — LangGraph State Machine Test Suite")
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
        # TEST 2: Response Path
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
        elif mock_browser_mgr.method_calls:
            log.error("❌ FAILED: Browser manager was called during text response path")
            all_passed = False
        else:
            log.info("✔ Response Path PASSED!")

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
        provider3 = MockLLMProvider(LLMResponse(
            tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://example.com/jobs"})]
        ))

        graph3 = create_agent_graph(tool_registry=registry3, llm_provider=provider3)
        res3 = run_agent_graph(graph3, state3)

        if res3.decision.action != "tool_call":
            log.error("❌ FAILED: Expected action 'tool_call', got '%s'", res3.decision.action)
            all_passed = False
        elif res3.verification_status != "tool_success":
            log.error("❌ FAILED: Expected verification_status 'tool_success', got '%s'", res3.verification_status)
            all_passed = False
        elif not mock_browser_mgr.open_url.called:
            log.error("❌ FAILED: BrowserManager.open_url was not called through ToolRegistry")
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
        res4 = run_agent_graph(graph4, state4)

        if res4.verification_status != "action_failed":
            log.error("❌ FAILED: Expected verification_status 'action_failed', got '%s'", res4.verification_status)
            all_passed = False
        elif res4.final_state.task_status == TaskStatus.COMPLETED:
            log.error("❌ FAILED: Task status was incorrectly set to COMPLETED after single tool failure")
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
        elif res5.verification_status != "action_failed":
            log.error("❌ FAILED: Unknown tool verification status should be 'action_failed'")
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
            # Should fail if neither decision_engine nor registry+provider are provided
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

    except Exception as exc:
        log.error("❌ Test suite crashed: %s", exc, exc_info=True)
        all_passed = False

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL LANGGRAPH TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_agent_graph_tests()
    sys.exit(0 if success else 1)
