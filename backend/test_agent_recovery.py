"""
test_agent_recovery.py — Verification test suite for Agent Recovery & Re-planning.

Run from backend/ directory:

    .venv\\Scripts\\python test_agent_recovery.py

All tests are mock-based (no real Playwright waits) for deterministic, fast execution.

Tests verified:
1.  Multi-cycle recovery: click(fail) → get_links → click(valid) → respond
2.  Failed action does NOT fabricate success in state
3.  Failure observation/error enters AgentState correctly
4.  Next LLM decision prompt contains failure information
5.  Repeated identical failed actions are stopped by existing loop protection
6.  Successful recovery does NOT auto-complete the task
7.  Normal successful workflow regression (open_url → get_page_text → respond)
8.  Safety boundary — no eval/exec/page.evaluate in production recovery path
9.  No hard-coded recovery sequence in production code
"""

import sys
import logging
import inspect
from typing import List
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")

from app.agent.state import AgentState, TaskStatus
from app.agent.tools import ToolRegistry
from app.agent.decision import AgentDecisionEngine, build_decision_prompt
from app.agent.graph import create_agent_graph, run_agent_graph
from app.llm.provider import LLMProvider, LLMResponse, LLMToolCall
from app.browser.manager import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class MockSequentialLLMProvider(LLMProvider):
    """Returns responses in sequence; repeats last response when exhausted."""

    def __init__(self, responses: List[LLMResponse]):
        self.responses = responses
        self.call_count = 0
        self.prompts_received: List[str] = []

    def generate(self, prompt, tools=None, system_instruction=None):
        self.prompts_received.append(prompt)
        if self.call_count < len(self.responses):
            res = self.responses[self.call_count]
        else:
            res = self.responses[-1]
        self.call_count += 1
        return res


def base_state() -> AgentState:
    return AgentState(
        task_id="recovery-test-001",
        user_goal="Find software engineering internships",
        task_status=TaskStatus.RUNNING,
    )


def make_failing_browser(click_error: str = "Element not found: timeout exceeded") -> MagicMock:
    """Return a mock BrowserManager whose click() always fails."""
    mock = MagicMock(spec=BrowserManager)
    mock.click.return_value = MagicMock(
        success=False,
        selector="#missing",
        url="https://example.com",
        error=click_error,
        observation=None,
    )
    return mock


def make_recovering_browser(valid_link_href: str = "https://example.com/page2") -> MagicMock:
    """
    Returns a mock BrowserManager that:
      - click("#does-not-exist")  → fails
      - get_links()               → returns one valid link
      - click("#valid-link")      → succeeds
    """
    mock = MagicMock(spec=BrowserManager)

    def click_side_effect(selector, timeout_ms=30000):
        if "does-not-exist" in selector or "missing" in selector:
            return MagicMock(
                success=False,
                selector=selector,
                url="https://example.com",
                error=f"Click failed: element '{selector}' not found",
                observation=None,
            )
        # Any other click (e.g. "#valid-link") succeeds
        return MagicMock(
            success=True,
            selector=selector,
            url=valid_link_href,
            error=None,
            observation=None,
        )

    mock.click.side_effect = click_side_effect

    from app.browser.schema import BrowserLink, BrowserLinksResult
    mock.get_links.return_value = BrowserLinksResult(
        success=True,
        url="https://example.com",
        links=[BrowserLink(text="Valid Link", url=valid_link_href)],
        truncated=False,
        error=None,
    )

    return mock


# ---------------------------------------------------------------------------
# TEST 1 — Multi-cycle recovery workflow
# ---------------------------------------------------------------------------

def test_recovery_multi_cycle() -> bool:
    """
    Cycle 1: click("#does-not-exist")  → fails
    Cycle 2: get_links()               → succeeds (recovery action)
    Cycle 3: click("#valid-link")      → succeeds
    Cycle 4: respond                   → task completes normally
    """
    log.info("\nTEST 1 · Multi-cycle recovery workflow…")

    mock_browser = make_recovering_browser()
    registry = ToolRegistry(mock_browser)

    responses = [
        LLMResponse(tool_calls=[LLMToolCall(name="click",     arguments={"selector": "#does-not-exist"})]),
        LLMResponse(tool_calls=[LLMToolCall(name="get_links", arguments={})]),
        LLMResponse(tool_calls=[LLMToolCall(name="click",     arguments={"selector": "#valid-link"})]),
        LLMResponse(text="Found the target page via recovery path."),
    ]
    provider = MockSequentialLLMProvider(responses)
    engine = AgentDecisionEngine(registry, provider)
    graph = create_agent_graph(decision_engine=engine, max_cycles=6)
    result = run_agent_graph(graph, initial_state=base_state(), max_cycles=6)

    passed = True

    # Cycle 1 failure must be in errors
    has_click_error = any(
        "click" in e.lower() or "does-not-exist" in e.lower() or "not found" in e.lower()
        for e in result.final_state.errors
    )
    if not has_click_error:
        log.error("  ❌ Expected click failure in state.errors; errors=%s", result.final_state.errors)
        passed = False

    # Task must end on normal respond path
    if result.stop_reason != "completed_response":
        log.error("  ❌ Expected stop_reason='completed_response', got '%s'", result.stop_reason)
        passed = False

    # Must have run at least 4 cycles (fail, recover, recover-click, respond)
    if result.cycle_count < 4:
        log.error("  ❌ Expected ≥4 cycles, ran %d", result.cycle_count)
        passed = False

    # get_links must appear in observations (proves recovery action executed)
    obs_sources = [o.source for o in result.final_state.observations]
    if not any("get_links" in s for s in obs_sources):
        log.error("  ❌ get_links recovery action not found in observations: %s", obs_sources)
        passed = False

    if passed:
        log.info("  ✔ Multi-cycle recovery workflow PASSED!")
    return passed


# ---------------------------------------------------------------------------
# TEST 2 — Failed action does NOT fabricate success
# ---------------------------------------------------------------------------

def test_failure_not_fabricated() -> bool:
    """
    click("#missing") fails.
    Verify the resulting tool_result.success == False and state.errors is populated.
    Verify state does NOT contain a fabricated success observation for that action.
    """
    log.info("\nTEST 2 · Failed action does not fabricate success…")

    mock_browser = make_failing_browser()
    registry = ToolRegistry(mock_browser)

    provider = MockSequentialLLMProvider([
        LLMResponse(tool_calls=[LLMToolCall(name="click", arguments={"selector": "#missing"})]),
        LLMResponse(text="Giving up."),
    ])
    engine = AgentDecisionEngine(registry, provider)

    state = base_state()
    result_cycle1 = engine.execute_cycle(state)

    passed = True

    # Tool result must report success=False
    tr = result_cycle1.tool_result
    actual_success = (
        tr.success if hasattr(tr, "success") else tr.get("success", True)
    )
    if actual_success:
        log.error("  ❌ tool_result.success should be False, got True")
        passed = False

    # state.errors must be non-empty
    if not result_cycle1.updated_state.errors:
        log.error("  ❌ state.errors should be non-empty after click failure")
        passed = False

    # Observations must contain a failure entry, not a success entry for that click
    click_obs = [
        o for o in result_cycle1.updated_state.observations
        if "click" in o.source
    ]
    if not click_obs:
        log.error("  ❌ No click observation found in state.observations")
        passed = False
    else:
        for obs in click_obs:
            if obs.metadata.get("success") is True:
                log.error("  ❌ Click observation incorrectly reports success=True: %s", obs)
                passed = False

    # Task status must NOT be COMPLETED
    if result_cycle1.updated_state.task_status == TaskStatus.COMPLETED:
        log.error("  ❌ task_status must not be COMPLETED after action failure")
        passed = False

    if passed:
        log.info("  ✔ Failed action does not fabricate success PASSED!")
    return passed


# ---------------------------------------------------------------------------
# TEST 3 — Failure enters AgentState correctly
# ---------------------------------------------------------------------------

def test_failure_in_agent_state() -> bool:
    """
    Verify that a browser tool failure produces a correctly structured
    Observation in AgentState.observations and an entry in AgentState.errors.
    """
    log.info("\nTEST 3 · Failure observation enters AgentState correctly…")

    mock_browser = make_failing_browser("Timeout: #internships not found after 30000ms")
    registry = ToolRegistry(mock_browser)

    provider = MockSequentialLLMProvider([
        LLMResponse(tool_calls=[LLMToolCall(name="click", arguments={"selector": "#internships"})]),
        LLMResponse(text="Done."),
    ])
    engine = AgentDecisionEngine(registry, provider)
    result = engine.execute_cycle(base_state())
    updated = result.updated_state

    passed = True

    # Source must be tool:click
    click_obs = [o for o in updated.observations if o.source == "tool:click"]
    if not click_obs:
        log.error("  ❌ Expected observation with source='tool:click'")
        passed = False
    else:
        obs = click_obs[0]
        if "fail" not in obs.summary.lower() and "error" not in obs.summary.lower():
            log.error("  ❌ Observation summary does not mention failure: '%s'", obs.summary)
            passed = False
        if obs.metadata.get("success") is not False:
            log.error("  ❌ Observation metadata.success should be False")
            passed = False

    # Errors list must be non-empty
    if not updated.errors:
        log.error("  ❌ state.errors should be non-empty")
        passed = False

    if passed:
        log.info("  ✔ Failure enters AgentState correctly PASSED!")
    return passed


# ---------------------------------------------------------------------------
# TEST 4 — Next LLM decision prompt contains failure information
# ---------------------------------------------------------------------------

def test_failure_in_next_prompt() -> bool:
    """
    After a click failure, the NEXT LLM generate() call should receive a prompt
    that includes the failure summary and/or error message.
    """
    log.info("\nTEST 4 · Failure information reaches the next LLM prompt…")

    mock_browser = make_failing_browser("Element #ghost not found")
    registry = ToolRegistry(mock_browser)

    responses = [
        LLMResponse(tool_calls=[LLMToolCall(name="click", arguments={"selector": "#ghost"})]),
        LLMResponse(text="Recovery response."),
    ]
    provider = MockSequentialLLMProvider(responses)
    engine = AgentDecisionEngine(registry, provider)
    graph = create_agent_graph(decision_engine=engine, max_cycles=4)
    run_agent_graph(graph, initial_state=base_state(), max_cycles=4)

    passed = True

    if len(provider.prompts_received) < 2:
        log.error("  ❌ Expected at least 2 prompts, got %d", len(provider.prompts_received))
        return False

    prompt_cycle2 = provider.prompts_received[1]
    # The prompt must contain failure context in observations or errors section
    failure_keywords = ["fail", "error", "not found", "#ghost"]
    if not any(kw in prompt_cycle2.lower() for kw in failure_keywords):
        log.error(
            "  ❌ Cycle-2 prompt doesn't include failure context.\n  Snippet: %s",
            prompt_cycle2[:400],
        )
        passed = False

    if passed:
        log.info("  ✔ Failure information reaches next LLM prompt PASSED!")
    return passed


# ---------------------------------------------------------------------------
# TEST 5 — Repeated failed actions stopped by existing loop protection
# ---------------------------------------------------------------------------

def test_repeated_failure_stopped() -> bool:
    """
    Mocked LLM keeps returning click("#missing") — same failing action 3+ times.
    Existing consecutive-duplicate-action protection must stop the loop.
    """
    log.info("\nTEST 5 · Repeated identical failed actions stopped by loop protection…")

    mock_browser = make_failing_browser()
    registry = ToolRegistry(mock_browser)

    # All 5 cycles return the identical failing action
    responses = [
        LLMResponse(tool_calls=[LLMToolCall(name="click", arguments={"selector": "#never-there"})]),
    ] * 5
    provider = MockSequentialLLMProvider(responses)
    engine = AgentDecisionEngine(registry, provider)
    graph = create_agent_graph(decision_engine=engine, max_cycles=6)
    result = run_agent_graph(graph, initial_state=base_state(), max_cycles=6)

    passed = True

    if result.stop_reason != "consecutive_duplicate_action":
        log.error(
            "  ❌ Expected stop_reason='consecutive_duplicate_action', got '%s'",
            result.stop_reason,
        )
        passed = False

    # Loop protection message must be in observations or errors
    has_loop_msg = any(
        "loop" in e.lower() or "consecutive" in e.lower() or "duplicate" in e.lower()
        for e in result.final_state.errors
    )
    if not has_loop_msg:
        loop_obs = [
            o for o in result.final_state.observations
            if "loop" in o.source or "consecutive" in o.summary.lower()
        ]
        if not loop_obs:
            log.error("  ❌ Loop-protection message not found in errors or observations")
            passed = False

    if passed:
        log.info("  ✔ Repeated failed actions stopped by loop protection PASSED!")
    return passed


# ---------------------------------------------------------------------------
# TEST 6 — Successful recovery does NOT auto-complete the task
# ---------------------------------------------------------------------------

def test_recovery_not_auto_complete() -> bool:
    """
    click(fail) → get_links(success) — the task must NOT auto-complete after
    the recovery action succeeds. The loop must continue until the LLM responds.
    """
    log.info("\nTEST 6 · Successful recovery does not auto-complete the task…")

    from app.browser.schema import BrowserLink, BrowserLinksResult

    mock_browser = MagicMock(spec=BrowserManager)
    mock_browser.click.return_value = MagicMock(
        success=False, selector="#bad", url="", error="Not found", observation=None
    )
    mock_browser.get_links.return_value = BrowserLinksResult(
        success=True,
        url="https://example.com",
        links=[BrowserLink(text="Jobs", url="https://example.com/jobs")],
        truncated=False,
        error=None,
    )
    registry = ToolRegistry(mock_browser)

    responses = [
        LLMResponse(tool_calls=[LLMToolCall(name="click",     arguments={"selector": "#bad"})]),
        LLMResponse(tool_calls=[LLMToolCall(name="get_links", arguments={})]),
        LLMResponse(text="Done after recovery."),  # only this should end the task
    ]
    provider = MockSequentialLLMProvider(responses)
    engine = AgentDecisionEngine(registry, provider)
    graph = create_agent_graph(decision_engine=engine, max_cycles=5)
    result = run_agent_graph(graph, initial_state=base_state(), max_cycles=5)

    passed = True

    # Final stop must be the LLM's explicit respond, not a tool success
    if result.stop_reason != "completed_response":
        log.error(
            "  ❌ Expected 'completed_response', got '%s'", result.stop_reason
        )
        passed = False

    # Must have run exactly 3 cycles
    if result.cycle_count < 3:
        log.error("  ❌ Expected ≥3 cycles, got %d", result.cycle_count)
        passed = False

    if passed:
        log.info("  ✔ Successful recovery does not auto-complete the task PASSED!")
    return passed


# ---------------------------------------------------------------------------
# TEST 7 — Normal successful workflow regression
# ---------------------------------------------------------------------------

def test_normal_workflow_regression() -> bool:
    """
    open_url → get_page_text → respond still works exactly as before.
    No regressions introduced by recovery changes.
    """
    log.info("\nTEST 7 · Normal successful workflow regression…")

    mock_browser = MagicMock(spec=BrowserManager)
    mock_browser.open_url.return_value = MagicMock(
        success=True, url="https://example.com", title="Example", error=None, observation=None
    )
    mock_browser.get_page_text.return_value = MagicMock(
        success=True, url="https://example.com", text="Some content", truncated=False, error=None
    )
    registry = ToolRegistry(mock_browser)

    responses = [
        LLMResponse(tool_calls=[LLMToolCall(name="open_url",      arguments={"url": "https://example.com"})]),
        LLMResponse(tool_calls=[LLMToolCall(name="get_page_text",  arguments={})]),
        LLMResponse(text="Task completed successfully."),
    ]
    provider = MockSequentialLLMProvider(responses)
    engine = AgentDecisionEngine(registry, provider)
    graph = create_agent_graph(decision_engine=engine, max_cycles=5)
    result = run_agent_graph(graph, initial_state=base_state(), max_cycles=5)

    passed = True

    if result.stop_reason != "completed_response":
        log.error("  ❌ Expected 'completed_response', got '%s'", result.stop_reason)
        passed = False

    if result.cycle_count != 3:
        log.error("  ❌ Expected 3 cycles, got %d", result.cycle_count)
        passed = False

    if result.final_state.errors:
        log.error("  ❌ Unexpected errors in normal workflow: %s", result.final_state.errors)
        passed = False

    if passed:
        log.info("  ✔ Normal successful workflow regression PASSED!")
    return passed


# ---------------------------------------------------------------------------
# TEST 8 — Safety boundary
# ---------------------------------------------------------------------------

def test_safety_boundary() -> bool:
    """
    Verify the recovery path does not introduce eval/exec/page.evaluate/subprocess.
    All actions must flow through AgentDecisionEngine → ApprovalGate → ToolRegistry.
    """
    log.info("\nTEST 8 · Safety boundary — no arbitrary execution in recovery path…")

    import app.agent.decision as dec_mod
    import app.agent.graph as graph_mod
    import app.agent.runner as runner_mod

    forbidden = ["eval(", "exec(", "subprocess", "os.system", "__import__(", ".evaluate("]
    passed = True

    for mod, name in [
        (dec_mod,    "decision.py"),
        (graph_mod,  "graph.py"),
        (runner_mod, "runner.py"),
    ]:
        code = inspect.getsource(mod)
        for kw in forbidden:
            if kw in code:
                log.error("  ❌ Forbidden keyword '%s' found in %s", kw, name)
                passed = False

    if passed:
        log.info("  ✔ Safety boundary PASSED!")
    return passed


# ---------------------------------------------------------------------------
# TEST 9 — No hard-coded recovery sequence in production code
# ---------------------------------------------------------------------------

def test_no_hardcoded_recovery() -> bool:
    """
    Verify production code contains no hard-coded recovery logic such as
    'if click fails → call get_links'. Recovery must be fully LLM-driven.
    """
    log.info("\nTEST 9 · No hard-coded recovery sequence in production code…")

    import app.agent.graph as graph_mod
    import app.agent.decision as dec_mod

    # Patterns that would indicate hard-coded recovery
    hard_coded_patterns = [
        "click_fail",
        "fallback_to_get_links",
        "retry_click",
        "on_click_error",
        "recover_click",
    ]
    passed = True
    for mod, name in [(graph_mod, "graph.py"), (dec_mod, "decision.py")]:
        code = inspect.getsource(mod).lower()
        for pat in hard_coded_patterns:
            if pat in code:
                log.error("  ❌ Hard-coded recovery pattern '%s' found in %s", pat, name)
                passed = False

    if passed:
        log.info("  ✔ No hard-coded recovery sequence PASSED!")
    return passed


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_recovery_tests() -> bool:
    log.info("=" * 65)
    log.info("AI Browser Agent — Recovery & Re-planning Test Suite")
    log.info("=" * 65)

    results = [
        test_recovery_multi_cycle(),
        test_failure_not_fabricated(),
        test_failure_in_agent_state(),
        test_failure_in_next_prompt(),
        test_repeated_failure_stopped(),
        test_recovery_not_auto_complete(),
        test_normal_workflow_regression(),
        test_safety_boundary(),
        test_no_hardcoded_recovery(),
    ]

    all_passed = all(results)

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL RECOVERY TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        failed_count = sum(1 for r in results if not r)
        log.error("OVERALL RESULT: %d TEST(S) FAILED.", failed_count)
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_recovery_tests()
    sys.exit(0 if success else 1)
