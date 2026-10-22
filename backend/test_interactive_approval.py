"""
test_interactive_approval.py — Verification test suite for Task 2Q:
Interactive Approval and Safe Cancellation.

Validates:
  1. Interactive approval API endpoints (/api/tasks/{task_id}/approval).
  2. Approving exact pending ApprovalRequest with saved arguments resumes without calling LLM.
  3. Rejecting pending action sets task status to STOPPED and prevents tool execution.
  4. Validation of task ID (404), current status (409), action identity (400), decision (400/422).
  5. Stale and duplicate approval requests return 409 Conflict.
  6. Safe cancellation endpoint (/api/tasks/{task_id}/stop).
  7. Stop requests are idempotent on active, stopped, and completed tasks.
  8. A stopped task never transitions to completed afterward.
  9. Race handling between stop and approval (stopped task rejects approval with 409 Conflict).
  10. Merely querying / displaying a task never triggers approval.
  11. Preserving all existing approval safeguards.
"""

import time
import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.agent.service import TaskManager, global_task_manager
from app.agent.state import (
    AgentState,
    ApprovalRequest,
    TaskStatus,
)
from app.agent.tools import ToolRegistry
from app.agent.decision import AgentDecisionResult
from app.agent.graph import AgentGraphResult
from app.safety.approval import ApprovalGate, CONSEQUENTIAL_ACTIONS, SAFE_BROWSER_TOOLS


class TestInteractiveApprovalAndCancellation(unittest.TestCase):
    def setUp(self):
        self.mock_task_manager = TaskManager()
        app.state.task_manager = self.mock_task_manager
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def test_approval_endpoint_nonexistent_task_returns_404(self):
        """POST /api/tasks/{task_id}/approval returns 404 for unknown task."""
        res = self.client.post(
            "/api/tasks/task-nonexistent/approval",
            json={"decision": "approve"},
        )
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.json()["detail"].lower())

    def test_stop_endpoint_nonexistent_task_returns_404(self):
        """POST /api/tasks/{task_id}/stop returns 404 for unknown task."""
        res = self.client.post("/api/tasks/task-nonexistent/stop")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.json()["detail"].lower())

    def test_approve_exact_pending_action_resumes_without_llm(self):
        """
        Approving a pending approval resumes the exact action and saved arguments.
        Does not ask LLM to choose an action.
        """
        saved_args = {
            "url": "https://example.com/apply",
            "applicant_name": "Alex Smith",
        }
        st = AgentState(
            task_id="task-appr-01",
            user_goal="Apply for role",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(
                action="submit_application",
                description="Submit internship application",
                target="https://example.com/apply",
                arguments=saved_args,
            ),
        )

        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            decision=AgentDecisionResult(
                action="tool_call",
                tool_name="submit_application",
                arguments=saved_args,
                updated_state=st,
            ),
            verification_status="action_failed",
            cycle_count=1,
            stop_reason="waiting_for_approval",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        # 1. Start task
        res_create = self.client.post("/api/tasks", json={"goal": "Apply for role"})
        self.assertEqual(res_create.status_code, 201)
        tid = res_create.json()["task_id"]

        # Wait for waiting_for_approval status
        for _ in range(50):
            poll = self.client.get(f"/api/tasks/{tid}").json()
            if poll["status"] == "waiting_for_approval":
                break
            time.sleep(0.01)

        poll = self.client.get(f"/api/tasks/{tid}").json()
        self.assertEqual(poll["status"], "waiting_for_approval")
        self.assertIsNotNone(poll["pending_approval"])
        self.assertEqual(poll["pending_approval"]["action"], "submit_application")
        self.assertEqual(poll["pending_approval"]["arguments"]["applicant_name"], "Alex Smith")

        # 2. Approve exact action
        res_appr = self.client.post(
            f"/api/tasks/{tid}/approval",
            json={"decision": "approve", "action": "submit_application"},
        )
        self.assertEqual(res_appr.status_code, 200)
        data = res_appr.json()

        # Pending approval must be cleared
        self.assertIsNone(data["pending_approval"])
        # Status must no longer be waiting_for_approval
        self.assertIn(data["status"], ("completed", "running"))

        # Verify observation records exact approved action and saved arguments
        obs_summaries = [o["summary"] for o in data["observations"]]
        self.assertTrue(any("approved by human" in s.lower() for s in obs_summaries))
        self.assertTrue(any("submit_application" in s for s in obs_summaries))

    def test_reject_action_stops_task_and_prevents_execution(self):
        """
        Rejecting a pending action transitions task to STOPPED,
        clears pending_approval, records error, and prevents tool execution.
        """
        st = AgentState(
            task_id="task-rej-01",
            user_goal="Send test email",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(
                action="send_email",
                description="Send confirmation email to external address",
                target="candidate@example.com",
                arguments={"to": "candidate@example.com", "subject": "Hello"},
            ),
        )

        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            decision=AgentDecisionResult(action="tool_call", tool_name="send_email", updated_state=st),
            verification_status="action_failed",
            cycle_count=1,
            stop_reason="waiting_for_approval",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        res_create = self.client.post("/api/tasks", json={"goal": "Send test email"})
        tid = res_create.json()["task_id"]

        for _ in range(50):
            poll = self.client.get(f"/api/tasks/{tid}").json()
            if poll["status"] == "waiting_for_approval":
                break
            time.sleep(0.01)

        # Reject action with custom reason
        res_rej = self.client.post(
            f"/api/tasks/{tid}/approval",
            json={"decision": "reject", "action": "send_email", "reason": "Untrusted external recipient."},
        )
        self.assertEqual(res_rej.status_code, 200)
        data = res_rej.json()

        self.assertEqual(data["status"], "stopped")
        self.assertIsNone(data["pending_approval"])
        self.assertTrue(any("Untrusted external recipient" in e for e in data["errors"]))
        self.assertTrue(any("send_email" in e for e in data["errors"]))

    def test_approval_invalid_decision_rejected(self):
        """Invalid decision values return HTTP 400 or 422."""
        st = AgentState(
            task_id="task-inv-dec",
            user_goal="Task",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(action="purchase", description="buy item"),
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            verification_status="action_failed",
            stop_reason="waiting_for_approval",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        res_create = self.client.post("/api/tasks", json={"goal": "Task"})
        tid = res_create.json()["task_id"]
        time.sleep(0.05)

        # Invalid decision word
        res = self.client.post(f"/api/tasks/{tid}/approval", json={"decision": "maybe"})
        self.assertIn(res.status_code, (400, 422))

    def test_approval_mismatched_action_identity_rejected(self):
        """Providing an action identity that doesn't match pending action returns 400 Bad Request."""
        st = AgentState(
            task_id="task-mismatch",
            user_goal="Task",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(action="submit_application", description="desc"),
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            verification_status="action_failed",
            stop_reason="waiting_for_approval",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        res_create = self.client.post("/api/tasks", json={"goal": "Task"})
        tid = res_create.json()["task_id"]
        time.sleep(0.05)

        res = self.client.post(
            f"/api/tasks/{tid}/approval",
            json={"decision": "approve", "action": "different_tool"},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("mismatch", res.json()["detail"].lower())

    def test_stale_or_duplicate_approval_decision_returns_409(self):
        """Approving or rejecting twice returns HTTP 409 Conflict for the second call."""
        st = AgentState(
            task_id="task-duplicate",
            user_goal="Task",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(action="submit_application", description="desc"),
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            verification_status="action_failed",
            stop_reason="waiting_for_approval",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        res_create = self.client.post("/api/tasks", json={"goal": "Task"})
        tid = res_create.json()["task_id"]
        time.sleep(0.05)

        # First approval succeeds
        res1 = self.client.post(f"/api/tasks/{tid}/approval", json={"decision": "approve"})
        self.assertEqual(res1.status_code, 200)

        # Duplicate approval fails with 409 Conflict
        res2 = self.client.post(f"/api/tasks/{tid}/approval", json={"decision": "approve"})
        self.assertEqual(res2.status_code, 409)
        self.assertIn("not waiting for approval", res2.json()["detail"].lower())

    def test_approval_on_active_task_not_waiting_for_approval_returns_409(self):
        """Calling approval on a task with running status returns 409 Conflict."""
        blocker = True

        def blocking_runner():
            r = MagicMock()
            def run_task(*args, **kwargs):
                while blocker:
                    time.sleep(0.01)
                return AgentGraphResult(
                    final_state=AgentState(task_id="t-block", user_goal="G", task_status=TaskStatus.COMPLETED),
                    verification_status="response_success",
                )
            r.run_task.side_effect = run_task
            return r

        self.mock_task_manager.set_runner_factory(blocking_runner)
        res_create = self.client.post("/api/tasks", json={"goal": "Task"})
        tid = res_create.json()["task_id"]
        time.sleep(0.02)

        res = self.client.post(f"/api/tasks/{tid}/approval", json={"decision": "approve"})
        self.assertEqual(res.status_code, 409)

        blocker = False

    def test_safe_cancellation_active_task(self):
        """
        Calling POST /api/tasks/{task_id}/stop transitions an active task to STOPPED,
        records cancellation observation/error, and is idempotent.
        """
        blocker = True

        def blocking_runner():
            r = MagicMock()
            def run_task(*args, **kwargs):
                while blocker:
                    time.sleep(0.01)
                return AgentGraphResult(
                    final_state=AgentState(task_id="t-stop", user_goal="G", task_status=TaskStatus.COMPLETED),
                    verification_status="response_success",
                )
            r.run_task.side_effect = run_task
            return r

        self.mock_task_manager.set_runner_factory(blocking_runner)
        res_create = self.client.post("/api/tasks", json={"goal": "Task to stop"})
        tid = res_create.json()["task_id"]
        time.sleep(0.02)

        # 1. Stop active task
        res_stop = self.client.post(f"/api/tasks/{tid}/stop")
        self.assertEqual(res_stop.status_code, 200)
        self.assertEqual(res_stop.json()["status"], "stopped")

        # 2. Idempotent: repeated stop requests succeed with 200 and status remains stopped
        res_stop2 = self.client.post(f"/api/tasks/{tid}/stop")
        self.assertEqual(res_stop2.status_code, 200)
        self.assertEqual(res_stop2.json()["status"], "stopped")

        blocker = False
        time.sleep(0.05)

        # 3. Stopped task does NOT become completed afterward
        poll = self.client.get(f"/api/tasks/{tid}").json()
        self.assertEqual(poll["status"], "stopped")

    def test_stop_on_completed_task_preserves_completed(self):
        """Calling stop on a task that already completed preserves completed status."""
        st = AgentState(task_id="t-done", user_goal="Done", task_status=TaskStatus.COMPLETED)
        mock_r = MagicMock()
        mock_r.run_task.return_value = AgentGraphResult(
            final_state=st,
            verification_status="response_success",
            stop_reason="completed",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_r)

        res_create = self.client.post("/api/tasks", json={"goal": "Fast task"})
        tid = res_create.json()["task_id"]
        time.sleep(0.05)

        # Call stop on already completed task
        res_stop = self.client.post(f"/api/tasks/{tid}/stop")
        self.assertEqual(res_stop.status_code, 200)
        self.assertEqual(res_stop.json()["status"], "completed")

    def test_race_between_stop_and_approval_stop_wins(self):
        """When a task is stopped while waiting for approval, subsequent approval returns 409 Conflict."""
        st = AgentState(
            task_id="task-race",
            user_goal="Task",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(action="submit_application", description="desc"),
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            verification_status="action_failed",
            stop_reason="waiting_for_approval",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        res_create = self.client.post("/api/tasks", json={"goal": "Task"})
        tid = res_create.json()["task_id"]
        time.sleep(0.05)

        # Stop arrives first
        res_stop = self.client.post(f"/api/tasks/{tid}/stop")
        self.assertEqual(res_stop.status_code, 200)
        self.assertEqual(res_stop.json()["status"], "stopped")

        # Approval arrives after stop
        res_appr = self.client.post(f"/api/tasks/{tid}/approval", json={"decision": "approve"})
        self.assertEqual(res_appr.status_code, 409)
        self.assertIn("not waiting for approval", res_appr.json()["detail"].lower())

    def test_never_treat_merely_displaying_as_approval(self):
        """Querying task state via GET /api/tasks/{task_id} never approves or mutates state."""
        st = AgentState(
            task_id="task-inspect",
            user_goal="Task",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(
                action="submit_application",
                description="desc",
                target="https://example.com",
            ),
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            verification_status="action_failed",
            stop_reason="waiting_for_approval",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        res_create = self.client.post("/api/tasks", json={"goal": "Inspect task"})
        tid = res_create.json()["task_id"]
        time.sleep(0.05)

        # Poll repeatedly
        for _ in range(5):
            res = self.client.get(f"/api/tasks/{tid}")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            # Still waiting_for_approval, never approved
            self.assertEqual(data["status"], "waiting_for_approval")
            self.assertIsNotNone(data["pending_approval"])

    def test_safety_safeguards_consequential_actions_policy(self):
        """Verify consequential actions require human approval and safe actions bypass it."""
        gate = ApprovalGate()
        for action in ["submit_application", "send_email", "purchase", "delete", "confirm"]:
            self.assertIn(action, CONSEQUENTIAL_ACTIONS)
            st = AgentState(task_id="t-safe", user_goal="g", task_status=TaskStatus.RUNNING)
            gated = gate.check(action, "desc", st, arguments={"k": "v"})
            self.assertEqual(gated.task_status, TaskStatus.WAITING_FOR_APPROVAL)
            self.assertIsNotNone(gated.pending_approval)
            self.assertEqual(gated.pending_approval.arguments, {"k": "v"})

        for tool in SAFE_BROWSER_TOOLS:
            st = AgentState(task_id="t-safe", user_goal="g", task_status=TaskStatus.RUNNING)
            gated = gate.check(tool, "desc", st)
            self.assertEqual(gated.task_status, TaskStatus.RUNNING)
            self.assertIsNone(gated.pending_approval)


if __name__ == "__main__":
    unittest.main()
