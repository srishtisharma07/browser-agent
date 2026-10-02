"""
test_agent_runner.py — End-to-End Verification Test Suite for AgentRunner & Autonomous Workflow.

Run from backend/ directory:

    .venv\\Scripts\\python test_agent_runner.py

Tests verified:
1. Multi-step autonomous workflow (Cycle 1: open_url -> Cycle 2: get_page_text -> Cycle 3: respond).
2. Browser tool result observation is preserved and passed to subsequent LLM prompts.
3. Tool failure is recorded accurately in state observations/errors.
4. Max-cycle protection stops execution when cycle limit is reached.
5. Security verification: no direct Playwright Page access, subprocess, shell, or eval/exec.
"""

import sys
import logging
import inspect
from typing import List
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from app.agent.state import AgentState, TaskStatus
from app.agent.tools import ToolRegistry
from app.agent.runner import AgentRunner, run_agent_task
from app.llm.provider import LLMProvider, LLMResponse, LLMToolCall
from app.browser.manager import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


class InspectingSequentialLLMProvider(LLMProvider):
    """
    Mock LLM provider that captures prompts passed to each decision cycle
    and returns a pre-configured sequence of LLMResponses.
    """
    def __init__(self, responses: List[LLMResponse]):
        self.responses = responses
        self.prompts_history: List[str] = []
        self.call_count = 0

    def generate(self, prompt, tools=None, system_instruction=None):
        self.prompts_history.append(prompt)
        if self.call_count < len(self.responses):
            res = self.responses[self.call_count]
        else:
            res = self.responses[-1]
        self.call_count += 1
        return res


def run_agent_runner_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — AgentRunner E2E Verification Test Suite")
    log.info("=" * 65)

    try:
        mock_browser_mgr = MagicMock(spec=BrowserManager)

        # ---------------------------------------------------------------------
        # TEST 1: Multi-Step Autonomous Workflow
        # ---------------------------------------------------------------------
        log.info("STEP 1 · Testing Multi-Step Autonomous Workflow (open_url -> get_page_text -> respond)…")
        mock_browser_mgr.reset_mock()
        mock_browser_mgr.open_url.return_value = {
            "success": True,
            "url": "https://www.python.org/",
            "error": None
        }
        mock_browser_mgr.get_page_text.return_value = {
            "success": True,
            "text": "Python is a programming language that lets you work quickly.",
            "url": "https://www.python.org/"
        }
        registry1 = ToolRegistry(mock_browser_mgr)

        responses1 = [
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://www.python.org/"})]),
            LLMResponse(tool_calls=[LLMToolCall(name="get_page_text", arguments={"max_length": 500})]),
            LLMResponse(text="Summary: Python is an efficient high-level programming language.")
        ]
        provider1 = InspectingSequentialLLMProvider(responses1)
        runner1 = AgentRunner(tool_registry=registry1, llm_provider=provider1)

        user_goal = "Research the Python programming language using https://www.python.org/"
        res1 = runner1.run_task(user_goal=user_goal, max_cycles=5)

        if res1.cycle_count != 3:
            log.error("❌ FAILED: Expected 3 cycles, got %d", res1.cycle_count)
            all_passed = False
        elif res1.stop_reason != "completed_response":
            log.error("❌ FAILED: Expected stop_reason 'completed_response', got '%s'", res1.stop_reason)
            all_passed = False
        elif res1.decision.response_text != "Summary: Python is an efficient high-level programming language.":
            log.error("❌ FAILED: Final response text mismatch")
            all_passed = False
        elif len(res1.final_state.observations) != 3:
            log.error("❌ FAILED: Observations count mismatch, expected 3, got %d", len(res1.final_state.observations))
            all_passed = False
        else:
            log.info("✔ Multi-Step Autonomous Workflow PASSED!")

        # ---------------------------------------------------------------------
        # TEST 2: Observation Persistence to Next Decision Prompt
        # ---------------------------------------------------------------------
        log.info("\nSTEP 2 · Testing Observation Persistence to Next Decision Prompt…")
        # Verify that prompt in Cycle 2 contained the Cycle 1 open_url observation
        prompt_cycle_2 = provider1.prompts_history[1] if len(provider1.prompts_history) > 1 else ""
        prompt_cycle_3 = provider1.prompts_history[2] if len(provider1.prompts_history) > 2 else ""

        if "tool:open_url" not in prompt_cycle_2 and "https://www.python.org/" not in prompt_cycle_2:
            log.error("❌ FAILED: Cycle 2 prompt did not receive Cycle 1 open_url observation: %s", prompt_cycle_2)
            all_passed = False
        elif "tool:get_page_text" not in prompt_cycle_3:
            log.error("❌ FAILED: Cycle 3 prompt did not receive Cycle 2 get_page_text observation: %s", prompt_cycle_3)
            all_passed = False
        else:
            log.info("✔ Observation Persistence PASSED!")

        # ---------------------------------------------------------------------
        # TEST 3: Tool Failure Recovery & Observation Logging
        # ---------------------------------------------------------------------
        log.info("\nSTEP 3 · Testing Tool Failure Recovery & Observation Logging…")
        mock_browser_mgr.reset_mock()
        mock_browser_mgr.open_url.return_value = {
            "success": False,
            "error": "ERR_NAME_NOT_RESOLVED",
            "url": "https://invalid-domain-xyz123.org"
        }
        registry3 = ToolRegistry(mock_browser_mgr)

        responses3 = [
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://invalid-domain-xyz123.org"})]),
            LLMResponse(text="Failed to reach website due to DNS failure.")
        ]
        provider3 = InspectingSequentialLLMProvider(responses3)
        runner3 = AgentRunner(tool_registry=registry3, llm_provider=provider3)

        res3 = runner3.run_task(user_goal="Check invalid site", max_cycles=5)

        if len(res3.final_state.errors) < 1 or "ERR_NAME_NOT_RESOLVED" not in res3.final_state.errors[0]:
            log.error("❌ FAILED: Error was not recorded accurately in state.errors")
            all_passed = False
        elif res3.final_state.observations[0].metadata.get("success") is not False:
            log.error("❌ FAILED: Observation success metadata was not False")
            all_passed = False
        else:
            log.info("✔ Tool Failure Recovery & Observation Logging PASSED!")

        # ---------------------------------------------------------------------
        # TEST 4: Max-Cycle Protection
        # ---------------------------------------------------------------------
        log.info("\nSTEP 4 · Testing Max-Cycle Protection (max_cycles=2)…")
        mock_browser_mgr.reset_mock()
        mock_browser_mgr.scroll.return_value = {"success": True, "url": "https://example.com"}
        registry4 = ToolRegistry(mock_browser_mgr)

        infinite_scroll_provider = InspectingSequentialLLMProvider([
            LLMResponse(tool_calls=[LLMToolCall(name="scroll", arguments={"direction": "down", "amount": 100})]),
            LLMResponse(tool_calls=[LLMToolCall(name="scroll", arguments={"direction": "down", "amount": 200})]),
            LLMResponse(tool_calls=[LLMToolCall(name="scroll", arguments={"direction": "down", "amount": 300})]),
        ])
        runner4 = AgentRunner(tool_registry=registry4, llm_provider=infinite_scroll_provider)

        res4 = runner4.run_task(user_goal="Scroll indefinitely", max_cycles=2)

        if res4.cycle_count != 2:
            log.error("❌ FAILED: Expected loop to terminate at cycle_count 2, got %d", res4.cycle_count)
            all_passed = False
        elif res4.stop_reason != "max_cycles_reached":
            log.error("❌ FAILED: Expected stop_reason 'max_cycles_reached', got '%s'", res4.stop_reason)
            all_passed = False
        else:
            log.info("✔ Max-Cycle Protection PASSED!")

        # ---------------------------------------------------------------------
        # TEST 5: Security Verification — No Direct Browser Bypass
        # ---------------------------------------------------------------------
        log.info("\nSTEP 5 · Testing Security Boundaries (No Direct Browser Bypass)…")
        from app.agent import runner as runner_module
        runner_code = inspect.getsource(runner_module)

        forbidden_keywords = ["page.evaluate", "subprocess", "os.system", "eval(", "exec("]
        for kw in forbidden_keywords:
            if kw in runner_code:
                log.error("❌ FAILED: Insecure keyword '%s' found in runner module", kw)
                all_passed = False
                break
        else:
            log.info("✔ Security Boundaries PASSED!")

    except Exception as exc:
        log.error("❌ Test suite crashed: %s", exc, exc_info=True)
        all_passed = False

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL AGENT RUNNER TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_agent_runner_tests()
    sys.exit(0 if success else 1)
