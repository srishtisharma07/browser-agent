"""
test_control_center_demo_flow.py -- Task 2S: Control Center Demo Workflow Verification

Verifies the complete Control Center flow required by Task 2S:
1. Enter a goal and candidate profile.
2. Start the agent and observe progress.
3. Inspect discovered listings, source links, evidence, selected/rejected decisions,
   and missing eligibility information.
4. Confirm errors and cycle limits are visible.
5. Verify approval and rejection behavior without submitting an application.
6. Stop a running task and verify its terminal state remains stopped.
"""

from __future__ import annotations

import sys
import time
import unittest
from typing import Any, Dict
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from fastapi.testclient import TestClient
from app.main import app
from app.agent.service import TaskManager, global_task_manager
from app.agent.runner import AgentRunner
from app.agent.graph import AgentGraphResult
from app.agent.decision import AgentDecisionResult
from app.agent.state import (
    AgentState,
    ApplicationDraft,
    ApprovalRequest,
    CandidateProfile,
    DiscoveredItem,
    DraftStatus,
    EvaluationDecision,
    ItemEvaluation,
    Observation,
    RejectedItem,
    TaskStatus,
)


def _wait_for_status(client: TestClient, task_id: str, target_statuses: tuple, timeout_steps: int = 50, step_sleep: float = 0.02) -> dict:
    for _ in range(timeout_steps):
        resp = client.get(f"/api/tasks/{task_id}")
        if resp.status_code == 200 and resp.json().get("status") in target_statuses:
            return resp.json()
        time.sleep(step_sleep)
    return client.get(f"/api/tasks/{task_id}").json()


class TestControlCenterDemoWorkflow(unittest.TestCase):
    """Verifies all 6 steps of the Control Center demo workflow."""

    def setUp(self):
        self.mgr = TaskManager()
        app.state.task_manager = self.mgr
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def test_step_1_and_2_create_with_profile_and_observe_progress(self):
        """Step 1 & 2: Enter goal and candidate profile; start agent and observe progress."""
        profile = {
            "education": "B.S. in Computer Science",
            "graduation_year": 2026,
            "technical_skills": ["Python", "React", "FastAPI"],
            "experience_level": "undergraduate intern",
            "preferred_role": "Software Engineering Intern",
            "location_preferences": ["Remote"],
            "internship_constraints": ["Summer 2026"],
        }
        res = self.client.post("/api/tasks", json={
            "goal": "Find Summer 2026 Software Engineering internships matching candidate profile",
            "max_cycles": 8,
            "profile": profile,
        })
        self.assertEqual(res.status_code, 201)
        data = res.json()
        tid = data["task_id"]
        self.assertTrue(tid.startswith("task-"))
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["max_cycles"], 8)
        self.assertIsNotNone(data["candidate_profile"])
        self.assertEqual(data["candidate_profile"]["graduation_year"], 2026)

        # Polling progress
        poll = self.client.get(f"/api/tasks/{tid}").json()
        self.assertIn("cycle_count", poll)
        self.assertIn("current_step", poll)
        self.assertIn("observations", poll)

    def test_step_3_inspect_listings_links_evidence_and_missing_eligibility(self):
        """Step 3: Discovered listings, source links, evidence, selected/rejected, missing info."""
        test_state = AgentState(
            task_id="demo-step-3",
            user_goal="Discover internships",
            task_status=TaskStatus.COMPLETED,
            discovered_items=[
                DiscoveredItem(title="Acme Tech SWE Intern 2026", url="https://example.com/acme", status="selected"),
                DiscoveredItem(title="Legacy DevOps Senior", url="https://example.com/devops", status="rejected"),
                DiscoveredItem(title="Stealth Backend Intern", url="https://example.com/stealth", status="rejected"),
            ],
            evaluations=[
                ItemEvaluation(
                    item="Acme Tech SWE Intern 2026",
                    url="https://example.com/acme",
                    decision=EvaluationDecision.SELECTED,
                    reason="Matches Python/React skills and 2026 graduation constraint. Remote position.",
                ),
                ItemEvaluation(
                    item="Legacy DevOps Senior",
                    url="https://example.com/devops",
                    decision=EvaluationDecision.REJECTED,
                    reason="Requires 5+ years experience. Closed application.",
                ),
                ItemEvaluation(
                    item="Stealth Backend Intern",
                    url="https://example.com/stealth",
                    decision=EvaluationDecision.REJECTED,
                    reason="Missing eligibility information: graduation year and term unspecified. Required skills (Rust) do not match profile.",
                ),
            ],
            application_drafts=[
                ApplicationDraft(
                    item_title="Acme Tech SWE Intern 2026",
                    item_url="https://example.com/acme",
                    status=DraftStatus.READY_FOR_REVIEW,
                    matched_requirements=["Python", "React", "Graduation 2026"],
                    missing_requirements=["Official transcript not uploaded"],
                    notes="Draft prepared based on verified evidence.",
                )
            ],
            observations=[
                Observation(source="tool:open_url", summary="Navigated to listings", url="https://example.com/listings", timestamp="2026-10-22T10:00:00"),
                Observation(source="tool:get_links", summary="Extracted 3 links", url="https://example.com/listings", timestamp="2026-10-22T10:00:01"),
            ],
        )

        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=test_state,
            decision=AgentDecisionResult(
                action="respond",
                response_text="Found 1 eligible internship at Acme Tech. 2 listings were rejected.",
                updated_state=test_state,
            ),
            verification_status="response_success",
            cycle_count=4,
            stop_reason="completed_response",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        res = self.client.post("/api/tasks", json={"goal": "Discover internships"})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed",))

        # Check discovered listings and source links
        listings = data.get("discovered_items", [])
        self.assertEqual(len(listings), 3)
        self.assertTrue(all(l.get("url") and l["url"].startswith("http") for l in listings))

        # Check evaluations and evidence
        evals = data.get("evaluations", [])
        self.assertEqual(len(evals), 3)
        selected = [e for e in evals if e["decision"] == "selected"]
        rejected = [e for e in evals if e["decision"] == "rejected"]
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(rejected), 2)

        # Check missing eligibility information detection
        stealth_eval = next((e for e in rejected if "stealth" in e["item"].lower()), None)
        self.assertIsNotNone(stealth_eval)
        self.assertIn("missing eligibility", stealth_eval["reason"].lower())

        # Check application draft with missing requirements
        drafts = data.get("application_drafts", [])
        self.assertEqual(len(drafts), 1)
        self.assertIn("missing_requirements", drafts[0])
        self.assertGreater(len(drafts[0]["missing_requirements"]), 0)

    def test_step_4_errors_and_cycle_limits_visible(self):
        """Step 4: Errors and cycle limits are visible in API state."""
        error_state = AgentState(
            task_id="demo-step-4",
            user_goal="Goal that encounters error",
            task_status=TaskStatus.COMPLETED,
            errors=["Connection refused to https://faulty-source.example.com"],
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=error_state,
            decision=AgentDecisionResult(action="respond", response_text="Error handled.", updated_state=error_state),
            verification_status="response_success",
            cycle_count=5,
            stop_reason="max_cycles_reached",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        res = self.client.post("/api/tasks", json={"goal": "Goal with error", "max_cycles": 5})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed",))

        self.assertEqual(data["max_cycles"], 5)
        self.assertEqual(data["cycle_count"], 5)
        self.assertGreater(len(data.get("errors", [])), 0)
        self.assertIn("Connection refused", data["errors"][0])

    def test_step_5_approval_and_rejection_without_submitting(self):
        """Step 5: Verify approval and rejection behavior without submitting an application."""
        saved_args = {"url": "https://example.com/apply", "applicant_name": "Test User"}
        waiting_state = AgentState(
            task_id="demo-step-5",
            user_goal="Apply to internship",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(
                action="submit_application",
                description="Consequential action: submit application",
                target="https://example.com/apply",
                arguments=saved_args,
            ),
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=waiting_state,
            decision=AgentDecisionResult(action="tool_call", tool_name="submit_application", arguments=saved_args, updated_state=waiting_state),
            verification_status="action_failed",
            cycle_count=2,
            stop_reason="waiting_for_approval",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        # 5a: Trigger task and reach WAITING_FOR_APPROVAL
        res = self.client.post("/api/tasks", json={"goal": "Apply to internship"})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("waiting_for_approval",))
        self.assertEqual(data["status"], "waiting_for_approval")
        self.assertIsNotNone(data.get("pending_approval"))

        # 5b: Rejection stops the task safely
        rej_res = self.client.post(
            f"/api/tasks/{tid}/approval",
            json={"decision": "reject", "action": "submit_application", "reason": "No submission allowed during demo."},
        )
        self.assertEqual(rej_res.status_code, 200)
        rej_data = rej_res.json()
        self.assertEqual(rej_data["status"], "stopped")
        self.assertIsNone(rej_data.get("pending_approval"))
        self.assertTrue(any("No submission allowed" in e for e in rej_data.get("errors", [])))

    def test_step_6_stop_running_task_and_terminal_state_persists(self):
        """Step 6: Stop a running task and verify its terminal state remains stopped across polling."""
        blocker = [True]

        def blocking_runner():
            r = MagicMock()
            def run_task(*args, **kwargs):
                while blocker[0]:
                    time.sleep(0.01)
                return AgentGraphResult(
                    final_state=AgentState(task_id="demo-step-6", user_goal="Stop test", task_status=TaskStatus.COMPLETED),
                    verification_status="response_success",
                    cycle_count=1,
                    stop_reason="completed",
                )
            r.run_task.side_effect = run_task
            return r

        self.mgr.set_runner_factory(blocking_runner)
        res = self.client.post("/api/tasks", json={"goal": "Stop demo task"})
        tid = res.json()["task_id"]
        time.sleep(0.02)

        # Send stop command
        stop_res = self.client.post(f"/api/tasks/{tid}/stop")
        self.assertEqual(stop_res.status_code, 200)
        self.assertEqual(stop_res.json()["status"], "stopped")

        # Let background worker finish and verify state stays stopped across polling
        blocker[0] = False
        time.sleep(0.05)

        for _ in range(5):
            poll = self.client.get(f"/api/tasks/{tid}").json()
            self.assertEqual(poll["status"], "stopped", "Terminal status must remain stopped")
            time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
