"""
test_approval.py — Verification test suite for Human-in-the-Loop Approval Safety Gate.

Run from backend/ directory:

    .venv\\Scripts\\python test_approval.py

Tests verified:
1. Safe browser action (open_url) does NOT require approval.
2. Consequential actions (submit_application, send_email) DO require approval.
3. Approval pauses execution: task_status = WAITING_FOR_APPROVAL, pending_approval set, action NOT executed.
4. Approved action clears pending_approval and restores RUNNING status.
5. Rejected action clears pending_approval, sets STOPPED, and records error.
6. Existing browser tools still execute via ToolRegistry without approval.
7. Security: approval module has no eval/exec/shell/Playwright access.
"""

import sys
import logging
import inspect
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from app.agent.state import AgentState, ApprovalRequest, TaskStatus
from app.agent.tools import ToolRegistry
from app.agent.decision import AgentDecisionEngine
from app.safety.approval import ApprovalGate, is_consequential, CONSEQUENTIAL_ACTIONS, SAFE_BROWSER_TOOLS
from app.llm.provider import LLMProvider, LLMResponse, LLMToolCall
from app.browser.manager import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


class MockLLMProvider(LLMProvider):
    def __init__(self, response: LLMResponse):
        self.response = response

    def generate(self, prompt, tools=None, system_instruction=None):
        return self.response


def base_state() -> AgentState:
    return AgentState(task_id="approval-test-001", user_goal="Test approval gate", task_status=TaskStatus.RUNNING)


def run_approval_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — Approval Safety Gate Test Suite")
    log.info("=" * 65)

    gate = ApprovalGate()

    # -------------------------------------------------------------------------
    # TEST 1: Safe action does NOT require approval
    # -------------------------------------------------------------------------
    log.info("STEP 1 · Testing safe actions do NOT require approval…")
    errors = []
    for tool in SAFE_BROWSER_TOOLS:
        if is_consequential(tool):
            errors.append(f"'{tool}' incorrectly flagged as consequential")
    if errors:
        for e in errors:
            log.error("❌ FAILED: %s", e)
        all_passed = False
    else:
        log.info("✔ All safe browser tools correctly bypass approval.")

    # Also verify gate.check leaves state unchanged for a safe tool
    st = base_state()
    result = gate.check("open_url", "Navigate to page", st)
    if result.task_status != TaskStatus.RUNNING or result.pending_approval is not None:
        log.error("❌ FAILED: gate.check mutated state for safe action 'open_url'")
        all_passed = False
    else:
        log.info("✔ Safe action (open_url) passes gate without state change PASSED!")

    # -------------------------------------------------------------------------
    # TEST 2: Consequential actions DO require approval
    # -------------------------------------------------------------------------
    log.info("\nSTEP 2 · Testing consequential actions DO require approval…")
    for action in ["submit_application", "send_email", "purchase", "delete", "confirm"]:
        if not is_consequential(action):
            log.error("❌ FAILED: '%s' should be consequential but is not", action)
            all_passed = False
        else:
            log.info("  ✔ '%s' correctly requires approval.", action)

    if all_passed:
        log.info("✔ Consequential action policy PASSED!")

    # -------------------------------------------------------------------------
    # TEST 3: Approval gate pauses execution
    # -------------------------------------------------------------------------
    log.info("\nSTEP 3 · Testing approval gate pauses execution before consequential action…")
    mock_browser = MagicMock(spec=BrowserManager)
    registry = ToolRegistry(mock_browser)

    # Inject a mock gate that records calls
    class TrackingGate(ApprovalGate):
        def __init__(self):
            self.checked_actions = []

        def check(self, action_name, description, state, target=None):
            self.checked_actions.append(action_name)
            return super().check(action_name, description, state, target)

    tracking_gate = TrackingGate()

    # Mock LLM requesting a consequential action
    provider3 = MockLLMProvider(LLMResponse(
        tool_calls=[LLMToolCall(name="submit_application", arguments={"url": "https://jobs.example.com"})]
    ))
    engine3 = AgentDecisionEngine(registry, provider3, approval_gate=tracking_gate)
    state3 = base_state()

    # submit_application is not in ToolRegistry — gate should intercept first
    result3 = engine3.execute_cycle(state3)

    if result3.updated_state.task_status != TaskStatus.WAITING_FOR_APPROVAL:
        log.error("❌ FAILED: task_status should be WAITING_FOR_APPROVAL, got '%s'", result3.updated_state.task_status)
        all_passed = False
    elif result3.updated_state.pending_approval is None:
        log.error("❌ FAILED: pending_approval should be set, got None")
        all_passed = False
    elif result3.updated_state.pending_approval.action != "submit_application":
        log.error("❌ FAILED: pending_approval.action mismatch: %s", result3.updated_state.pending_approval.action)
        all_passed = False
    elif result3.tool_result is not None:
        log.error("❌ FAILED: consequential action was executed (tool_result is not None)")
        all_passed = False
    elif mock_browser.method_calls:
        log.error("❌ FAILED: BrowserManager was called despite pending approval")
        all_passed = False
    else:
        log.info("✔ Approval gate correctly pauses execution PASSED!")

    # -------------------------------------------------------------------------
    # TEST 4: Approved action clears pending_approval
    # -------------------------------------------------------------------------
    log.info("\nSTEP 4 · Testing approved action clears pending_approval and restores RUNNING…")
    state4 = base_state()
    state4 = state4.model_copy(update={
        "task_status": TaskStatus.WAITING_FOR_APPROVAL,
        "pending_approval": ApprovalRequest(
            action="submit_application",
            description="Submit job application",
            target="https://jobs.example.com",
        ),
    })

    approved_state = gate.approve(state4)

    if approved_state.pending_approval is not None:
        log.error("❌ FAILED: pending_approval was not cleared after approval")
        all_passed = False
    elif approved_state.task_status != TaskStatus.RUNNING:
        log.error("❌ FAILED: task_status should be RUNNING after approval, got '%s'", approved_state.task_status)
        all_passed = False
    else:
        log.info("✔ Approval clears pending_approval and restores RUNNING PASSED!")

    # Verify ValueError when no pending approval exists
    try:
        gate.approve(base_state())
        log.error("❌ FAILED: Should raise ValueError when approving with no pending request")
        all_passed = False
    except ValueError:
        log.info("  ✔ ValueError correctly raised when no pending approval.")

    # -------------------------------------------------------------------------
    # TEST 5: Rejected action stops task
    # -------------------------------------------------------------------------
    log.info("\nSTEP 5 · Testing rejected action stops the task…")
    state5 = base_state()
    state5 = state5.model_copy(update={
        "task_status": TaskStatus.WAITING_FOR_APPROVAL,
        "pending_approval": ApprovalRequest(
            action="send_email",
            description="Send application confirmation email",
        ),
    })

    rejected_state = gate.reject(state5, reason="User declined email sending.")

    if rejected_state.pending_approval is not None:
        log.error("❌ FAILED: pending_approval was not cleared after rejection")
        all_passed = False
    elif rejected_state.task_status != TaskStatus.STOPPED:
        log.error("❌ FAILED: task_status should be STOPPED after rejection, got '%s'", rejected_state.task_status)
        all_passed = False
    elif not any("send_email" in e for e in rejected_state.errors):
        log.error("❌ FAILED: Rejection error was not recorded in state.errors")
        all_passed = False
    else:
        log.info("✔ Rejection stops task and records error PASSED!")

    # Verify ValueError when no pending approval exists
    try:
        gate.reject(base_state())
        log.error("❌ FAILED: Should raise ValueError when rejecting with no pending request")
        all_passed = False
    except ValueError:
        log.info("  ✔ ValueError correctly raised when no pending approval.")

    # -------------------------------------------------------------------------
    # TEST 6: Safe browser tools still execute normally via ToolRegistry
    # -------------------------------------------------------------------------
    log.info("\nSTEP 6 · Testing safe browser tools execute via ToolRegistry without approval…")
    mock_browser.reset_mock()
    mock_browser.open_url.return_value = {"success": True, "url": "https://python.org", "error": None}
    registry6 = ToolRegistry(mock_browser)
    provider6 = MockLLMProvider(LLMResponse(
        tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://python.org"})]
    ))
    engine6 = AgentDecisionEngine(registry6, provider6)
    state6 = base_state()

    result6 = engine6.execute_cycle(state6)

    if result6.updated_state.task_status == TaskStatus.WAITING_FOR_APPROVAL:
        log.error("❌ FAILED: safe tool 'open_url' was incorrectly gated for approval")
        all_passed = False
    elif result6.updated_state.pending_approval is not None:
        log.error("❌ FAILED: pending_approval was set for safe tool")
        all_passed = False
    elif not mock_browser.open_url.called:
        log.error("❌ FAILED: BrowserManager.open_url was not called for safe tool")
        all_passed = False
    else:
        log.info("✔ Safe browser tools execute via ToolRegistry without approval PASSED!")

    # -------------------------------------------------------------------------
    # TEST 7: Security verification
    # -------------------------------------------------------------------------
    log.info("\nSTEP 7 · Testing security boundaries in approval module…")
    from app.safety import approval as approval_mod
    code = inspect.getsource(approval_mod)
    forbidden = ["eval(", "exec(", "subprocess", "os.system", "__import__", "page.evaluate"]
    for kw in forbidden:
        if kw in code:
            log.error("❌ FAILED: Insecure keyword '%s' found in approval module", kw)
            all_passed = False
            break
    else:
        log.info("✔ Security boundaries PASSED!")

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL APPROVAL TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_approval_tests()
    sys.exit(0 if success else 1)
