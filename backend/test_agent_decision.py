"""
test_agent_decision.py — Focused test suite for Single Agent Decision Engine.

Run from backend/ directory:

    .venv\\Scripts\\python test_agent_decision.py

Tests verified:
1. Response path (no tool call): returns text response, no tool execution, state valid.
2. Tool-call path (valid tool call): executes via ToolRegistry boundary, observation recorded.
3. Multiple tool calls rejected safely.
4. Unknown tool rejected safely without browser action.
5. Invalid arguments caught by ToolRegistry boundary.
6. Tool execution failure recorded as observation/error.
7. Unrelated AgentState fields preserved across cycle.
8. Security boundary: no arbitrary Python, shell, eval/exec, or direct Playwright access.
"""

import sys
import logging
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from app.agent.state import AgentState, Constraint, DiscoveredItem, RejectedItem, TaskStatus
from app.agent.tools import ToolRegistry
from app.agent.decision import AgentDecisionEngine, AgentDecisionResult, build_decision_prompt
from app.llm.provider import LLMProvider, LLMResponse, LLMToolCall
from app.browser.manager import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


class MockLLMProvider(LLMProvider):
    """Fake LLM Provider for deterministic testing without external API calls."""

    def __init__(self, mock_response: LLMResponse):
        self.mock_response = mock_response
        self.last_prompt = None
        self.last_tools = None
        self.last_system_instruction = None

    def generate(self, prompt, tools=None, system_instruction=None):
        self.last_prompt = prompt
        self.last_tools = tools
        self.last_system_instruction = system_instruction
        return self.mock_response


def create_sample_state() -> AgentState:
    """Helper to create a populated AgentState."""
    return AgentState(
        task_id="task-test-001",
        user_goal="Find remote Python engineer jobs",
        extracted_constraints=[
            Constraint(name="role", value="Python Engineer"),
            Constraint(name="type", value="Remote"),
        ],
        current_plan=["Navigate to job board", "Extract job postings"],
        completed_steps=[],
        current_step=None,
        discovered_items=[
            DiscoveredItem(title="Python Dev", url="https://example.com/job1")
        ],
        rejected_items=[
            RejectedItem(title="Java Dev", url="https://example.com/job2", reason="Wrong language")
        ],
        task_status=TaskStatus.RUNNING,
    )


def run_agent_decision_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — Decision Engine Verification Test Suite")
    log.info("=" * 65)

    try:
        # Mock BrowserManager to prevent launching real Chromium unless explicitly needed
        mock_browser_mgr = MagicMock(spec=BrowserManager)

        # ---------------------------------------------------------------------
        # TEST 1: Response Path (No Tool Calls)
        # ---------------------------------------------------------------------
        log.info("STEP 1 · Testing Response Path (Direct Text Response)…")
        state1 = create_sample_state()
        registry1 = ToolRegistry(mock_browser_mgr)

        text_response = LLMResponse(text="Found 1 matching job posting: Python Dev.")
        provider1 = MockLLMProvider(text_response)
        engine1 = AgentDecisionEngine(registry1, provider1)

        result1 = engine1.execute_cycle(state1)

        if result1.action != "respond":
            log.error("❌ FAILED: Expected action 'respond', got '%s'", result1.action)
            all_passed = False
        elif result1.response_text != "Found 1 matching job posting: Python Dev.":
            log.error("❌ FAILED: Response text mismatch")
            all_passed = False
        elif mock_browser_mgr.method_calls:
            log.error("❌ FAILED: Browser manager was called during text response path")
            all_passed = False
        elif len(result1.updated_state.observations) != 1:
            log.error("❌ FAILED: Observation was not added to state")
            all_passed = False
        else:
            log.info("✔ Response Path PASSED!")

        # ---------------------------------------------------------------------
        # TEST 2: Tool-Call Path (Single Valid Tool)
        # ---------------------------------------------------------------------
        log.info("\nSTEP 2 · Testing Tool-Call Path (open_url execution)…")
        state2 = create_sample_state()
        mock_browser_mgr.open_url.return_value = {
            "success": True,
            "url": "https://example.com/jobs",
            "error": None
        }
        registry2 = ToolRegistry(mock_browser_mgr)

        tool_response = LLMResponse(
            tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://example.com/jobs"})]
        )
        provider2 = MockLLMProvider(tool_response)
        engine2 = AgentDecisionEngine(registry2, provider2)

        result2 = engine2.execute_cycle(state2)

        if result2.action != "tool_call":
            log.error("❌ FAILED: Expected action 'tool_call', got '%s'", result2.action)
            all_passed = False
        elif result2.tool_name != "open_url":
            log.error("❌ FAILED: Tool name mismatch")
            all_passed = False
        elif result2.arguments.get("url") != "https://example.com/jobs":
            log.error("❌ FAILED: Tool arguments mismatch")
            all_passed = False
        elif not mock_browser_mgr.open_url.called:
            log.error("❌ FAILED: BrowserManager.open_url was not called")
            all_passed = False
        elif len(result2.updated_state.observations) != 1:
            log.error("❌ FAILED: Tool observation not added")
            all_passed = False
        elif result2.updated_state.observations[0].source != "tool:open_url":
            log.error("❌ FAILED: Tool observation source mismatch")
            all_passed = False
        else:
            log.info("✔ Tool-Call Path PASSED!")

        # ---------------------------------------------------------------------
        # TEST 3: Multiple Tool Calls Rejection
        # ---------------------------------------------------------------------
        log.info("\nSTEP 3 · Testing Multiple Tool Calls Rejection…")
        state3 = create_sample_state()
        mock_browser_mgr.reset_mock()
        registry3 = ToolRegistry(mock_browser_mgr)

        multi_tool_response = LLMResponse(
            tool_calls=[
                LLMToolCall(name="open_url", arguments={"url": "https://example.com"}),
                LLMToolCall(name="click", arguments={"selector": "#btn"}),
            ]
        )
        provider3 = MockLLMProvider(multi_tool_response)
        engine3 = AgentDecisionEngine(registry3, provider3)

        result3 = engine3.execute_cycle(state3)

        if result3.action != "error":
            log.error("❌ FAILED: Multiple tool calls were not rejected with action 'error'")
            all_passed = False
        elif mock_browser_mgr.method_calls:
            log.error("❌ FAILED: Browser action was executed despite multiple tool calls")
            all_passed = False
        elif len(result3.updated_state.errors) != 1:
            log.error("❌ FAILED: Error not recorded in state")
            all_passed = False
        else:
            log.info("✔ Multiple Tool Calls Rejection PASSED!")

        # ---------------------------------------------------------------------
        # TEST 4: Unknown Tool Rejection
        # ---------------------------------------------------------------------
        log.info("\nSTEP 4 · Testing Unknown Tool Rejection…")
        state4 = create_sample_state()
        mock_browser_mgr.reset_mock()
        registry4 = ToolRegistry(mock_browser_mgr)

        unknown_tool_response = LLMResponse(
            tool_calls=[LLMToolCall(name="delete_everything", arguments={})]
        )
        provider4 = MockLLMProvider(unknown_tool_response)
        engine4 = AgentDecisionEngine(registry4, provider4)

        result4 = engine4.execute_cycle(state4)

        if result4.action != "error":
            log.error("❌ FAILED: Unknown tool was not rejected with action 'error'")
            all_passed = False
        elif mock_browser_mgr.method_calls:
            log.error("❌ FAILED: Browser executed action for unknown tool")
            all_passed = False
        elif "delete_everything" not in result4.response_text:
            log.error("❌ FAILED: Error text did not mention unknown tool name")
            all_passed = False
        else:
            log.info("✔ Unknown Tool Rejection PASSED!")

        # ---------------------------------------------------------------------
        # TEST 5: Invalid Arguments Handling
        # ---------------------------------------------------------------------
        log.info("\nSTEP 5 · Testing Invalid Arguments Handling…")
        state5 = create_sample_state()
        mock_browser_mgr.reset_mock()
        registry5 = ToolRegistry(mock_browser_mgr)

        # open_url requires 'url' string, missing here
        invalid_args_response = LLMResponse(
            tool_calls=[LLMToolCall(name="open_url", arguments={"timeout_ms": 5000})]
        )
        provider5 = MockLLMProvider(invalid_args_response)
        engine5 = AgentDecisionEngine(registry5, provider5)

        result5 = engine5.execute_cycle(state5)

        if result5.action != "tool_call":
            log.error("❌ FAILED: Expected action 'tool_call' representing attempted execution")
            all_passed = False
        elif mock_browser_mgr.open_url.called:
            log.error("❌ FAILED: BrowserManager was called despite invalid Pydantic args")
            all_passed = False
        elif result5.tool_result.get("success") is not False:
            log.error("❌ FAILED: ToolRegistry did not report success=False for invalid args")
            all_passed = False
        elif len(result5.updated_state.errors) != 1:
            log.error("❌ FAILED: Error was not logged to AgentState")
            all_passed = False
        else:
            log.info("✔ Invalid Arguments Handling PASSED!")

        # ---------------------------------------------------------------------
        # TEST 6: Tool Execution Failure Handling
        # ---------------------------------------------------------------------
        log.info("\nSTEP 6 · Testing Tool Execution Failure Handling…")
        state6 = create_sample_state()
        mock_browser_mgr.reset_mock()
        mock_browser_mgr.click.return_value = {
            "success": False,
            "error": "Element '#nonexistent' not found after 30000ms",
            "url": "https://example.com"
        }
        registry6 = ToolRegistry(mock_browser_mgr)

        click_response = LLMResponse(
            tool_calls=[LLMToolCall(name="click", arguments={"selector": "#nonexistent"})]
        )
        provider6 = MockLLMProvider(click_response)
        engine6 = AgentDecisionEngine(registry6, provider6)

        result6 = engine6.execute_cycle(state6)

        if result6.action != "tool_call":
            log.error("❌ FAILED: Expected action 'tool_call'")
            all_passed = False
        elif result6.tool_result.get("success") is not False:
            log.error("❌ FAILED: Tool result should reflect failure")
            all_passed = False
        elif len(result6.updated_state.errors) != 1:
            log.error("❌ FAILED: Tool failure was not added to state.errors")
            all_passed = False
        elif "Element '#nonexistent' not found" not in result6.updated_state.observations[0].summary:
            log.error("❌ FAILED: Tool failure observation summary mismatch")
            all_passed = False
        else:
            log.info("✔ Tool Execution Failure Handling PASSED!")

        # ---------------------------------------------------------------------
        # TEST 7: AgentState Preservation
        # ---------------------------------------------------------------------
        log.info("\nSTEP 7 · Testing AgentState Preservation…")
        state7 = create_sample_state()
        registry7 = ToolRegistry(mock_browser_mgr)
        provider7 = MockLLMProvider(text_response)
        engine7 = AgentDecisionEngine(registry7, provider7)

        result7 = engine7.execute_cycle(state7)

        st = result7.updated_state
        if st.task_id != "task-test-001":
            log.error("❌ FAILED: task_id altered")
            all_passed = False
        elif st.user_goal != "Find remote Python engineer jobs":
            log.error("❌ FAILED: user_goal altered")
            all_passed = False
        elif len(st.extracted_constraints) != 2:
            log.error("❌ FAILED: extracted_constraints altered")
            all_passed = False
        elif len(st.discovered_items) != 1 or st.discovered_items[0].title != "Python Dev":
            log.error("❌ FAILED: discovered_items altered")
            all_passed = False
        elif len(st.rejected_items) != 1 or st.rejected_items[0].title != "Java Dev":
            log.error("❌ FAILED: rejected_items altered")
            all_passed = False
        else:
            log.info("✔ AgentState Preservation PASSED!")

        # ---------------------------------------------------------------------
        # TEST 8: Security Boundary Verification
        # ---------------------------------------------------------------------
        log.info("\nSTEP 8 · Testing Security Boundaries…")

        # Prompt verification
        prompt_text = build_decision_prompt(state7)
        if "eval(" in prompt_text or "exec(" in prompt_text or "import os" in prompt_text:
            log.error("❌ FAILED: Insecure code keywords found in prompt")
            all_passed = False
        
        # Ensure engine contains no eval/exec/import dynamic code execution
        import inspect
        from app.agent import decision as decision_mod
        code_str = inspect.getsource(decision_mod)

        if "eval(" in code_str or "exec(" in code_str or "__import__" in code_str:
            log.error("❌ FAILED: Dynamic code execution function found in decision module")
            all_passed = False
        else:
            log.info("✔ Security Boundaries PASSED!")

    except Exception as exc:
        log.error("❌ Test suite crashed: %s", exc, exc_info=True)
        all_passed = False

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL AGENT DECISION TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_agent_decision_tests()
    sys.exit(0 if success else 1)
