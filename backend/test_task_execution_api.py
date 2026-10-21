"""
Deterministic Unit Tests for Task 2O -- Task Execution API & Control Center Integration.

Validates:
  1. Starting a task via POST /api/tasks and receiving unique task_id immediately.
  2. Retrieving task status via GET /api/tasks/{task_id} with full structured data.
  3. Running, completed, failed, and waiting_for_approval states.
  4. Preventing duplicate active task starts (HTTP 409 Conflict).
  5. Safe handling of missing Gemini configuration (LLMConfigurationError) without server crash.
  6. Empty goal rejection (HTTP 422/400).
  7. Nonexistent task lookup returns HTTP 404.
  8. Preserving approval safety and human-in-the-loop pending approval request.
  9. Listing tasks via GET /api/tasks.
"""

import time
import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.agent.service import TaskManager, global_task_manager
from app.agent.state import (
    AgentState,
    ApplicationDraft,
    ApprovalRequest,
    DiscoveredItem,
    DraftStatus,
    EvaluationDecision,
    ItemEvaluation,
    Observation,
    TaskStatus,
)
from app.agent.decision import AgentDecisionResult
from app.agent.graph import AgentGraphResult
from app.config import LLMConfigurationError


class TestTaskExecutionAPI(unittest.TestCase):
    def setUp(self):
        # Create fresh TaskManager for test isolation
        self.mock_task_manager = TaskManager()
        app.state.task_manager = self.mock_task_manager
        self.client = TestClient(app)

    def tearDown(self):
        # Reset to global task manager
        app.state.task_manager = global_task_manager

    def test_create_task_success(self):
        """Starting a task returns HTTP 201 with unique task_id and running status immediately."""
        # Create mock runner that simulates execution
        mock_runner = MagicMock()
        st = AgentState(task_id="test-1", user_goal="Find internships", task_status=TaskStatus.COMPLETED)
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            decision=AgentDecisionResult(action="respond", response_text="Found 3 matches.", updated_state=st),
            verification_status="response_success",
            cycle_count=1,
            stop_reason="completed_response",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        response = self.client.post("/api/tasks", json={"goal": "Find internships", "max_cycles": 3})
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("task_id", data)
        self.assertTrue(data["task_id"].startswith("task-"))
        self.assertEqual(data["goal"], "Find internships")
        self.assertIn(data["status"], ("running", "completed"))

    def test_create_task_empty_goal_rejected(self):
        """Empty or whitespace goal is rejected."""
        response = self.client.post("/api/tasks", json={"goal": "   "})
        self.assertIn(response.status_code, (400, 422))

    def test_prevent_duplicate_concurrent_tasks(self):
        """Prevent starting a second task while one is currently running."""
        blocker_started = False
        unblock_event = False

        # Runner that blocks until flag is set
        def blocking_runner():
            runner = MagicMock()
            def run_task(*args, **kwargs):
                nonlocal blocker_started
                blocker_started = True
                while not unblock_event:
                    time.sleep(0.01)
                return AgentGraphResult(
                    final_state=AgentState(task_id="t-block", user_goal="Block", task_status=TaskStatus.COMPLETED),
                    verification_status="response_success",
                    cycle_count=1,
                    stop_reason="completed",
                )
            runner.run_task.side_effect = run_task
            return runner

        self.mock_task_manager.set_runner_factory(blocking_runner)

        # Start first task
        res1 = self.client.post("/api/tasks", json={"goal": "Task 1"})
        self.assertEqual(res1.status_code, 201)

        # Wait until first task is confirmed running
        for _ in range(50):
            if blocker_started:
                break
            time.sleep(0.01)

        # Attempt to start second task while first is active
        res2 = self.client.post("/api/tasks", json={"goal": "Task 2"})
        self.assertEqual(res2.status_code, 409)
        self.assertIn("already running", res2.json()["detail"])

        # Release first task
        unblock_event = True

    def test_get_task_by_id_and_results(self):
        """Retrieving task returns all observations, evaluations, drafts, and responses."""
        st = AgentState(
            task_id="task-results-01",
            user_goal="Find software jobs",
            task_status=TaskStatus.COMPLETED,
            observations=[
                Observation(
                    source="open_url",
                    summary="Loaded search page",
                    url="https://example.com/jobs",
                    timestamp="2026-10-21T12:00:00",
                )
            ],
            discovered_items=[
                DiscoveredItem(title="SWE Intern", url="https://example.com/job1")
            ],
            evaluations=[
                ItemEvaluation(
                    item="SWE Intern",
                    url="https://example.com/job1",
                    decision=EvaluationDecision.SELECTED,
                    reason="Matches requirements",
                )
            ],
            application_drafts=[
                ApplicationDraft(
                    item_title="SWE Intern",
                    item_url="https://example.com/job1",
                    status=DraftStatus.READY_FOR_REVIEW,
                    matched_requirements=["Python"],
                    notes="Draft ready",
                )
            ],
        )

        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            decision=AgentDecisionResult(action="respond", response_text="Application prepared for SWE Intern.", updated_state=st),
            verification_status="response_success",
            cycle_count=2,
            stop_reason="completed_response",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        res = self.client.post("/api/tasks", json={"goal": "Find software jobs"})
        self.assertEqual(res.status_code, 201)
        tid = res.json()["task_id"]

        # Wait briefly for thread to finish
        for _ in range(50):
            poll = self.client.get(f"/api/tasks/{tid}").json()
            if poll["status"] == "completed":
                break
            time.sleep(0.02)

        data = self.client.get(f"/api/tasks/{tid}").json()
        self.assertEqual(data["task_id"], tid)
        self.assertEqual(data["status"], "completed")
        self.assertEqual(len(data["observations"]), 1)
        self.assertEqual(data["observations"][0]["summary"], "Loaded search page")
        self.assertEqual(len(data["evaluations"]), 1)
        self.assertEqual(data["evaluations"][0]["decision"], "selected")
        self.assertEqual(len(data["application_drafts"]), 1)
        self.assertEqual(data["application_drafts"][0]["item_title"], "SWE Intern")
        self.assertEqual(data["final_response"], "Application prepared for SWE Intern.")

    def test_get_nonexistent_task_returns_404(self):
        """Nonexistent task ID returns HTTP 404."""
        response = self.client.get("/api/tasks/task-doesnotexist")
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"].lower())

    def test_missing_gemini_config_error_handling(self):
        """When Gemini configuration is missing, task status is failed and server does not crash."""
        def missing_config_runner():
            runner = MagicMock()
            runner.run_task.side_effect = LLMConfigurationError(
                "GEMINI_API_KEY environment variable is missing or empty. Please set GEMINI_API_KEY in your environment or .env file."
            )
            return runner

        self.mock_task_manager.set_runner_factory(missing_config_runner)

        response = self.client.post("/api/tasks", json={"goal": "Research topics"})
        self.assertEqual(response.status_code, 201)
        tid = response.json()["task_id"]

        # Wait for worker thread to catch error
        for _ in range(50):
            poll = self.client.get(f"/api/tasks/{tid}").json()
            if poll["status"] == "failed":
                break
            time.sleep(0.02)

        poll = self.client.get(f"/api/tasks/{tid}").json()
        self.assertEqual(poll["status"], "failed")
        self.assertTrue(len(poll["errors"]) > 0)
        self.assertIn("GEMINI_API_KEY environment variable is missing", poll["errors"][0])

    def test_approval_safety_preservation(self):
        """When agent requires human approval, status is waiting_for_approval and approval details are exposed."""
        st = AgentState(
            task_id="task-appr",
            user_goal="Submit test",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(
                action="submit_form",
                description="Needs approval before submitting application",
                target="https://example.com/apply",
            ),
        )

        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=st,
            decision=AgentDecisionResult(action="tool_call", tool_name="submit_form", updated_state=st),
            verification_status="action_failed",
            cycle_count=1,
            stop_reason="waiting_for_approval",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        response = self.client.post("/api/tasks", json={"goal": "Submit test"})
        tid = response.json()["task_id"]

        for _ in range(50):
            poll = self.client.get(f"/api/tasks/{tid}").json()
            if poll["status"] == "waiting_for_approval":
                break
            time.sleep(0.02)

        poll = self.client.get(f"/api/tasks/{tid}").json()
        self.assertEqual(poll["status"], "waiting_for_approval")
        self.assertIsNotNone(poll["pending_approval"])
        self.assertEqual(poll["pending_approval"]["action"], "submit_form")

    def test_list_tasks(self):
        """GET /api/tasks lists all stored tasks."""
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=AgentState(task_id="t1", user_goal="Goal 1", task_status=TaskStatus.COMPLETED),
            verification_status="response_success",
            cycle_count=1,
            stop_reason="completed",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        self.client.post("/api/tasks", json={"goal": "Goal 1"})
        time.sleep(0.05)

        res = self.client.get("/api/tasks")
        self.assertEqual(res.status_code, 200)
        tasks = res.json()["tasks"]
        self.assertTrue(len(tasks) >= 1)
        self.assertEqual(tasks[0]["goal"], "Goal 1")


if __name__ == "__main__":
    unittest.main()
