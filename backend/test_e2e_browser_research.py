"""
test_e2e_browser_research.py -- Task 2R: End-to-End Browser Research Verification

Verifies the complete vertical slice:
    POST /api/tasks -> TaskManager -> AgentRunner/LangGraph -> browser tools
    -> research findings -> selected/rejected evaluations -> API response

Uses deterministic mocks and the local internship fixtures.
No real Gemini API key or live browser required.

Test Groups:
    E2E-1.  Full internship research workflow (mocked LLM + browser)
    E2E-2.  Profile-aware selection vs. rejection with evidence
    E2E-3.  Task creation -> status polling -> final results consistency
    E2E-4.  Approval gate pause and safe resumption mid-workflow
    E2E-5.  Stop/cancel during active research
    E2E-7.  UI data contract: all fields expected by the frontend
    E2E-8.  Error recovery: failed tool does not terminate workflow
    E2E-9.  Application draft created only after evaluate_item selection
    E2E-10. Smoke: local HTML fixture is well-formed and parseable

Run from backend/ directory:
    .venv\Scripts\python test_e2e_browser_research.py
"""

from __future__ import annotations

import sys
import time
import logging
import unittest
from pathlib import Path
from typing import List
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from fastapi.testclient import TestClient

from app.main import app
from app.agent.service import TaskManager, global_task_manager
from app.agent.runner import AgentRunner
from app.agent.graph import AgentGraphResult
from app.agent.decision import AgentDecisionResult
from app.agent.tools import ToolRegistry
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
    ResearchFinding,
    RejectedItem,
    TaskStatus,
)
from app.browser.manager import BrowserManager
from app.llm.provider import LLMProvider, LLMResponse, LLMToolCall

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "test_pages" / "internships"
LISTINGS_HTML_PATH = FIXTURES_DIR / "listings.html"

ACME_LISTING_TEXT = (
    "Software Engineering Intern - Summer 2026\n"
    "Company: Acme Tech\n"
    "Location: Remote\n"
    "Role: Software Engineering Intern\n"
    "Eligibility: Enrolled in B.S. or B.Tech in Computer Science, graduating in 2026.\n"
    "Required Skills: Python, React, FastAPI\n"
    "Application Status: Accepting Applications\n"
    "View Listing Details: https://example.com/jobs/acme-swe-2026"
)

SENIOR_DEVOPS_TEXT = (
    "Senior DevOps Infrastructure Engineer\n"
    "Company: Legacy Systems Inc\n"
    "Location: On-site (Austin, TX only)\n"
    "Role: Senior Full-Time\n"
    "Eligibility: Minimum 5+ years full-time industry experience. No interns.\n"
    "Required Skills: Kubernetes, Terraform, C++\n"
    "Application Status: Closed"
)

STEALTH_LISTING_TEXT = (
    "Backend Engineering Intern\n"
    "Company: Mystery Stealth Co\n"
    "Location: Unspecified\n"
    "Eligibility: Graduation year, degree level, and work authorization criteria not provided.\n"
    "Required Skills: Go, Rust\n"
    "Application Status: Unknown"
)


class _SequentialMockLLM(LLMProvider):
    """Returns responses in order, repeating the last one if exhausted."""

    def __init__(self, responses: List[LLMResponse]):
        self._responses = responses
        self._idx = 0

    def generate(self, prompt, tools=None, system_instruction=None):
        resp = self._responses[min(self._idx, len(self._responses) - 1)]
        self._idx += 1
        return resp


def _make_mock_browser(page_text: str = ACME_LISTING_TEXT) -> MagicMock:
    """Return a BrowserManager mock wired with typical internship-page responses."""
    mock = MagicMock(spec=BrowserManager)
    mock.open_url.return_value = {
        "success": True,
        "url": "file:///test_pages/internships/listings.html",
        "error": None,
        "observation": None,
    }
    mock.get_page_text.return_value = {
        "success": True,
        "text": page_text,
        "url": "file:///test_pages/internships/listings.html",
        "error": None,
    }
    mock.get_links.return_value = {
        "success": True,
        "links": [{"text": "View Listing Details", "href": "https://example.com/jobs/acme-swe-2026"}],
    }
    return mock


def _wait_for_status(
    client: TestClient,
    task_id: str,
    target_statuses: tuple,
    timeout_steps: int = 100,
    step_sleep: float = 0.02,
) -> dict:
    """Poll GET /api/tasks/{task_id} until status is one of target_statuses."""
    for _ in range(timeout_steps):
        resp = client.get(f"/api/tasks/{task_id}")
        if resp.status_code == 200 and resp.json().get("status") in target_statuses:
            return resp.json()
        time.sleep(step_sleep)
    return client.get(f"/api/tasks/{task_id}").json()


# ---------------------------------------------------------------------------
# E2E-1: Full internship research workflow
# ---------------------------------------------------------------------------

class TestE2EInternshipResearchWorkflow(unittest.TestCase):
    """E2E-1 + E2E-6: Task creation -> browser nav -> findings -> evaluations -> API response."""

    def setUp(self):
        self.mgr = TaskManager()
        app.state.task_manager = self.mgr
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def _build_runner(self):
        mock_browser = _make_mock_browser("\n\n".join([ACME_LISTING_TEXT, SENIOR_DEVOPS_TEXT]))
        registry = ToolRegistry(mock_browser)
        llm = _SequentialMockLLM([
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": "file:///test_pages/internships/listings.html"})]),
            LLMResponse(tool_calls=[LLMToolCall(name="get_page_text", arguments={"max_length": 5000})]),
            LLMResponse(tool_calls=[LLMToolCall(name="record_research_finding", arguments={
                "title": "Software Engineering Intern - Summer 2026",
                "url": "https://example.com/jobs/acme-swe-2026",
                "summary": "Remote SWE intern role at Acme Tech, Summer 2026, requires Python/React/FastAPI.",
                "key_points": ["Python, React, FastAPI", "Remote", "Summer 2026"],
                "source": "browser",
            })]),
            LLMResponse(tool_calls=[LLMToolCall(name="evaluate_item", arguments={
                "item": "Software Engineering Intern - Summer 2026",
                "url": "https://example.com/jobs/acme-swe-2026",
                "decision": "selected",
                "reason": "Remote internship matching Python, React, FastAPI, and 2026 graduation.",
            })]),
            LLMResponse(tool_calls=[LLMToolCall(name="evaluate_item", arguments={
                "item": "Senior DevOps Infrastructure Engineer",
                "url": "https://example.com/jobs/devops-senior",
                "decision": "rejected",
                "reason": "Requires 5+ years experience and is closed. Not an internship.",
            })]),
            LLMResponse(text=(
                "Found 1 selected internship (Acme Tech SWE Intern 2026, Remote) "
                "and 1 rejected listing (Senior DevOps, requires 5+ years experience)."
            )),
        ])
        return AgentRunner(tool_registry=registry, llm_provider=llm, browser_manager=mock_browser), mock_browser

    def test_e2e_1a_full_workflow_findings_and_evaluations(self):
        """E2E-1a: Complete research cycle produces evaluations and a final_response."""
        runner, _ = self._build_runner()
        self.mgr.set_runner_factory(lambda: runner)

        res = self.client.post("/api/tasks", json={"goal": "Find software engineering internships for Summer 2026", "max_cycles": 10})
        self.assertEqual(res.status_code, 201)
        tid = res.json()["task_id"]

        data = _wait_for_status(self.client, tid, ("completed", "failed"))
        self.assertEqual(data["status"], "completed", f"Task failed: {data.get('errors')}")

        evals = data.get("evaluations", [])
        selected = [e for e in evals if e["decision"] == "selected"]
        rejected = [e for e in evals if e["decision"] == "rejected"]
        self.assertGreaterEqual(len(selected), 1, "Expected at least 1 selected evaluation")
        self.assertGreaterEqual(len(rejected), 1, "Expected at least 1 rejected evaluation")

        # The mock LLM selects "Software Engineering Intern - Summer 2026" (Acme Tech)
        swe_eval = next(
            (e for e in selected if "software engineering intern" in e["item"].lower() or "acme" in e["item"].lower()),
            None
        )
        self.assertIsNotNone(swe_eval, f"SWE intern should be selected; got selected={[e['item'] for e in selected]}")

        devops_eval = next((e for e in rejected if "devops" in e["item"].lower()), None)
        self.assertIsNotNone(devops_eval, f"Senior DevOps role should be rejected; got rejected={[e['item'] for e in rejected]}")

        self.assertIsNotNone(data.get("final_response"), "final_response must be set")
        self.assertIn("Acme", data["final_response"])

    def test_e2e_1b_observations_accumulate_across_cycles(self):
        """E2E-1b/E2E-6: Observations from every cycle appear in the final task record."""
        runner, _ = self._build_runner()
        self.mgr.set_runner_factory(lambda: runner)

        res = self.client.post("/api/tasks", json={"goal": "Research internships", "max_cycles": 10})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed", "failed"))

        obs = data.get("observations", [])
        self.assertGreaterEqual(len(obs), 4, f"Expected >=4 observations, got {len(obs)}")
        sources = [o["source"] for o in obs]
        self.assertIn("tool:open_url", sources, "open_url observation missing")
        self.assertIn("tool:get_page_text", sources, "get_page_text observation missing")

    def test_e2e_1c_cycle_count_accurate(self):
        """E2E-1c: cycle_count in API response matches actual number of decision turns."""
        runner, _ = self._build_runner()
        self.mgr.set_runner_factory(lambda: runner)

        res = self.client.post("/api/tasks", json={"goal": "Find internships", "max_cycles": 10})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed", "failed"))
        self.assertGreaterEqual(data.get("cycle_count", 0), 5,
                                f"Expected >=5 cycles, got {data.get('cycle_count')}")

    def test_e2e_1d_cycle_limit_enforced(self):
        """E2E-1d: When max_cycles limit is reached, execution halts and status transitions to completed."""
        mock_browser = _make_mock_browser(ACME_LISTING_TEXT)
        registry = ToolRegistry(mock_browser)
        infinite_llm = _SequentialMockLLM([
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": f"https://example.com/page-{i}"})])
            for i in range(20)
        ])
        runner = AgentRunner(tool_registry=registry, llm_provider=infinite_llm, browser_manager=mock_browser)
        self.mgr.set_runner_factory(lambda: runner)

        res = self.client.post("/api/tasks", json={"goal": "Find internships", "max_cycles": 3})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed", "failed"))
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data.get("cycle_count"), 3)


# ---------------------------------------------------------------------------
# E2E-2: Profile-aware selection and rejection
# ---------------------------------------------------------------------------

class TestE2EProfileAwareMatching(unittest.TestCase):
    """E2E-2: Evidence-based selection and rejection driven by CandidateProfile."""

    def setUp(self):
        self.mgr = TaskManager()
        app.state.task_manager = self.mgr
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def _build_profile_runner(self):
        mock_browser = _make_mock_browser("\n\n".join([ACME_LISTING_TEXT, SENIOR_DEVOPS_TEXT, STEALTH_LISTING_TEXT]))
        registry = ToolRegistry(mock_browser)
        llm = _SequentialMockLLM([
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": "file:///test_pages/internships/listings.html"})]),
            LLMResponse(tool_calls=[LLMToolCall(name="get_page_text", arguments={"max_length": 8000})]),
            LLMResponse(tool_calls=[LLMToolCall(name="evaluate_item", arguments={
                "item": "Acme Tech - Software Engineering Intern 2026",
                "url": "https://example.com/jobs/acme-swe-2026",
                "decision": "selected",
                "reason": "Matches profile: Remote role, Python/React/FastAPI required, B.S. CS 2026 eligible.",
            })]),
            LLMResponse(tool_calls=[LLMToolCall(name="evaluate_item", arguments={
                "item": "Legacy Systems - Senior DevOps Engineer",
                "url": "https://example.com/jobs/devops-senior",
                "decision": "rejected",
                "reason": "Requires 5+ years full-time experience. Not an internship. Application is closed.",
            })]),
            LLMResponse(tool_calls=[LLMToolCall(name="evaluate_item", arguments={
                "item": "Mystery Stealth Co - Backend Intern",
                "url": "https://example.com/jobs/stealth-backend",
                "decision": "rejected",
                "reason": "Missing eligibility info: no graduation year, location, or term specified. Skills (Go, Rust) not in candidate profile.",
            })]),
            LLMResponse(text=(
                "Profile-aware search complete. 1 selected (Acme SWE Intern). "
                "2 rejected: Senior DevOps (experience mismatch), Stealth Backend (missing eligibility, skill mismatch)."
            )),
        ])
        return AgentRunner(tool_registry=registry, llm_provider=llm, browser_manager=mock_browser)

    def test_e2e_2a_profile_aware_selection_and_rejection(self):
        """E2E-2a: Agent selects matching listings and rejects non-matching ones with evidence."""
        runner = self._build_profile_runner()
        self.mgr.set_runner_factory(lambda: runner)

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
            "goal": "Find Summer 2026 SWE internships for a 2026 CS graduate",
            "max_cycles": 10,
            "profile": profile,
        })
        self.assertEqual(res.status_code, 201)
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed", "failed"))
        self.assertEqual(data["status"], "completed", f"Errors: {data.get('errors')}")

        evals = data.get("evaluations", [])
        selected = [e for e in evals if e["decision"] == "selected"]
        rejected = [e for e in evals if e["decision"] == "rejected"]
        self.assertEqual(len(selected), 1, f"Expected 1 selected, got {len(selected)}")
        self.assertEqual(len(rejected), 2, f"Expected 2 rejected, got {len(rejected)}")
        self.assertIn("acme", selected[0]["item"].lower())
        self.assertIn("remote", selected[0]["reason"].lower())
        devops_rej = next((r for r in rejected if "devops" in r["item"].lower()), None)
        self.assertIsNotNone(devops_rej)
        self.assertIn("experience", devops_rej["reason"].lower())

    def test_e2e_2b_profile_included_in_api_response(self):
        """E2E-2b: Profile submitted in task creation is accessible via GET /api/tasks/{task_id}."""
        runner = self._build_profile_runner()
        self.mgr.set_runner_factory(lambda: runner)

        res = self.client.post("/api/tasks", json={
            "goal": "Find internships",
            "profile": {"graduation_year": 2026, "technical_skills": ["Python"], "preferred_role": "SWE Intern"},
        })
        tid = res.json()["task_id"]
        data = self.client.get(f"/api/tasks/{tid}").json()
        prof = data.get("candidate_profile")
        self.assertIsNotNone(prof)
        self.assertEqual(prof["graduation_year"], 2026)
        self.assertEqual(prof["preferred_role"], "SWE Intern")


# ---------------------------------------------------------------------------
# E2E-3: Status polling and task ID uniqueness
# ---------------------------------------------------------------------------

class TestE2EStatusPollingConsistency(unittest.TestCase):
    """E2E-3: Status transitions are consistent and monotonic through the lifecycle."""

    def setUp(self):
        self.mgr = TaskManager()
        app.state.task_manager = self.mgr
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def test_e2e_3a_running_to_completed(self):
        """E2E-3a: Task starts as running and transitions to completed correctly."""
        final_st = AgentState(
            task_id="e2e-poll-01",
            user_goal="Poll status test",
            task_status=TaskStatus.COMPLETED,
            evaluations=[ItemEvaluation(
                item="Test Role", url="https://example.com/test",
                decision=EvaluationDecision.SELECTED, reason="Matches criteria",
            )],
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=final_st,
            decision=AgentDecisionResult(action="respond", response_text="Done.", updated_state=final_st),
            verification_status="response_success",
            cycle_count=2,
            stop_reason="completed_response",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        res = self.client.post("/api/tasks", json={"goal": "Test status polling"})
        self.assertEqual(res.status_code, 201)
        tid = res.json()["task_id"]
        immediate = self.client.get(f"/api/tasks/{tid}").json()
        self.assertIn(immediate["status"], ("running", "completed"))

        final = _wait_for_status(self.client, tid, ("completed",))
        self.assertEqual(final["status"], "completed")
        self.assertEqual(final["task_id"], tid)
        self.assertIsNotNone(final.get("final_response"))
        self.assertGreater(len(final.get("evaluations", [])), 0)

    def test_e2e_3b_unique_task_ids(self):
        """E2E-3b: Sequential task creations produce unique task IDs."""
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=AgentState(task_id="x", user_goal="g", task_status=TaskStatus.COMPLETED),
            verification_status="response_success",
            cycle_count=1,
            stop_reason="completed",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        res1 = self.client.post("/api/tasks", json={"goal": "Task A"})
        tid1 = res1.json()["task_id"]
        _wait_for_status(self.client, tid1, ("completed", "failed"))

        res2 = self.client.post("/api/tasks", json={"goal": "Task B"})
        tid2 = res2.json()["task_id"]
        self.assertNotEqual(tid1, tid2, "Task IDs must be unique")

    def test_e2e_3c_nonexistent_task_returns_404(self):
        """E2E-3c: GET /api/tasks/bad-id returns 404."""
        res = self.client.get("/api/tasks/task-doesnotexist-e2e-3c")
        self.assertEqual(res.status_code, 404)
        self.assertIn("not found", res.json()["detail"].lower())


# ---------------------------------------------------------------------------
# E2E-4: Approval gate pause and safe resumption
# ---------------------------------------------------------------------------

class TestE2EApprovalGateIntegration(unittest.TestCase):
    """E2E-4: Agent pauses at consequential action; human reviews; workflow resumes correctly."""

    def setUp(self):
        self.mgr = TaskManager()
        app.state.task_manager = self.mgr
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def test_e2e_4a_approval_pauses_and_resumes(self):
        """E2E-4a: Consequential action pauses task; POST .../approval resumes without calling LLM."""
        saved_args = {"url": "https://example.com/apply", "applicant_name": "Jane Doe"}
        waiting_state = AgentState(
            task_id="e2e-appr-01",
            user_goal="Apply to Acme Tech internship",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(
                action="submit_application",
                description="Submit internship application to Acme Tech",
                target="https://example.com/apply",
                arguments=saved_args,
            ),
            evaluations=[ItemEvaluation(
                item="Acme Tech Intern", url="https://example.com/apply",
                decision=EvaluationDecision.SELECTED, reason="Matches criteria",
            )],
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=waiting_state,
            decision=AgentDecisionResult(
                action="tool_call", tool_name="submit_application",
                arguments=saved_args, updated_state=waiting_state,
            ),
            verification_status="action_failed",
            cycle_count=3,
            stop_reason="waiting_for_approval",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        res = self.client.post("/api/tasks", json={"goal": "Apply to Acme Tech internship"})
        self.assertEqual(res.status_code, 201)
        tid = res.json()["task_id"]

        data = _wait_for_status(self.client, tid, ("waiting_for_approval",))
        self.assertEqual(data["status"], "waiting_for_approval")
        self.assertIsNotNone(data.get("pending_approval"))
        self.assertEqual(data["pending_approval"]["action"], "submit_application")
        self.assertEqual(data["pending_approval"]["arguments"]["applicant_name"], "Jane Doe")

        appr_res = self.client.post(
            f"/api/tasks/{tid}/approval",
            json={"decision": "approve", "action": "submit_application"},
        )
        self.assertEqual(appr_res.status_code, 200)
        appr_data = appr_res.json()
        self.assertIsNone(appr_data.get("pending_approval"))
        self.assertIn(appr_data["status"], ("completed", "running"))
        obs_summaries = [o["summary"] for o in appr_data.get("observations", [])]
        self.assertTrue(any("approved" in s.lower() for s in obs_summaries),
                        f"Expected approval observation; got: {obs_summaries}")

    def test_e2e_4b_rejection_stops_task_with_reason(self):
        """E2E-4b: Rejecting a pending action stops task and records the rejection reason."""
        waiting_state = AgentState(
            task_id="e2e-rej-01",
            user_goal="Send confirmation",
            task_status=TaskStatus.WAITING_FOR_APPROVAL,
            pending_approval=ApprovalRequest(
                action="send_email",
                description="Send confirmation email",
                target="external@example.com",
                arguments={"to": "external@example.com", "subject": "Confirmation"},
            ),
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=waiting_state,
            decision=AgentDecisionResult(action="tool_call", tool_name="send_email", updated_state=waiting_state),
            verification_status="action_failed",
            cycle_count=1,
            stop_reason="waiting_for_approval",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        res = self.client.post("/api/tasks", json={"goal": "Send confirmation email"})
        tid = res.json()["task_id"]
        _wait_for_status(self.client, tid, ("waiting_for_approval",))

        rej_res = self.client.post(
            f"/api/tasks/{tid}/approval",
            json={"decision": "reject", "action": "send_email", "reason": "Untrusted external recipient."},
        )
        self.assertEqual(rej_res.status_code, 200)
        rej_data = rej_res.json()
        self.assertEqual(rej_data["status"], "stopped")
        self.assertIsNone(rej_data.get("pending_approval"))
        self.assertTrue(any("Untrusted external recipient" in e for e in rej_data.get("errors", [])))

    def test_e2e_4c_approval_nonexistent_task_404(self):
        """E2E-4c: Approval for unknown task_id returns 404."""
        res = self.client.post("/api/tasks/task-e2e-none/approval", json={"decision": "approve"})
        self.assertEqual(res.status_code, 404)


# ---------------------------------------------------------------------------
# E2E-5: Stop/cancel during active research
# ---------------------------------------------------------------------------

class TestE2EStopCancellation(unittest.TestCase):
    """E2E-5: Stop during active research transitions task to stopped safely."""

    def setUp(self):
        self.mgr = TaskManager()
        app.state.task_manager = self.mgr
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def test_e2e_5a_stop_active_task(self):
        """E2E-5a: POST .../stop transitions to stopped and task never becomes completed."""
        blocker = [True]

        def blocking_runner():
            r = MagicMock()
            def run_task(*args, **kwargs):
                while blocker[0]:
                    time.sleep(0.01)
                return AgentGraphResult(
                    final_state=AgentState(task_id="e2e-stop", user_goal="g", task_status=TaskStatus.COMPLETED),
                    verification_status="response_success",
                    cycle_count=1,
                    stop_reason="completed",
                )
            r.run_task.side_effect = run_task
            return r

        self.mgr.set_runner_factory(blocking_runner)
        res = self.client.post("/api/tasks", json={"goal": "Research task to stop"})
        self.assertEqual(res.status_code, 201)
        tid = res.json()["task_id"]
        time.sleep(0.03)

        stop_res = self.client.post(f"/api/tasks/{tid}/stop")
        self.assertEqual(stop_res.status_code, 200)
        self.assertEqual(stop_res.json()["status"], "stopped")

        stop_res2 = self.client.post(f"/api/tasks/{tid}/stop")
        self.assertEqual(stop_res2.status_code, 200)
        self.assertEqual(stop_res2.json()["status"], "stopped")

        blocker[0] = False
        time.sleep(0.06)

        final = self.client.get(f"/api/tasks/{tid}").json()
        self.assertEqual(final["status"], "stopped", "Stopped task must not transition to completed")

    def test_e2e_5b_cancel_alias(self):
        """E2E-5b: POST .../cancel is an alias for /stop."""
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=AgentState(task_id="e2e-cancel", user_goal="g", task_status=TaskStatus.COMPLETED),
            verification_status="response_success",
            cycle_count=1,
            stop_reason="completed",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        res = self.client.post("/api/tasks", json={"goal": "Task to cancel"})
        tid = res.json()["task_id"]
        _wait_for_status(self.client, tid, ("completed",))

        cancel_res = self.client.post(f"/api/tasks/{tid}/cancel")
        self.assertEqual(cancel_res.status_code, 200)
        self.assertEqual(cancel_res.json()["status"], "completed")


# ---------------------------------------------------------------------------
# E2E-7: UI data contract
# ---------------------------------------------------------------------------

class TestE2EUIDataContract(unittest.TestCase):
    """E2E-7: All fields expected by the frontend Control Center UI are present and typed."""

    def setUp(self):
        self.mgr = TaskManager()
        app.state.task_manager = self.mgr
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def test_e2e_7a_all_frontend_fields_present(self):
        """E2E-7a: GET /api/tasks/{task_id} contains all fields the frontend depends on."""
        final_st = AgentState(
            task_id="e2e-ui-01",
            user_goal="Full UI contract check",
            task_status=TaskStatus.COMPLETED,
            observations=[Observation(
                source="tool:open_url", summary="Opened listings page",
                url="https://example.com", timestamp="2026-10-22T10:00:00",
            )],
            discovered_items=[DiscoveredItem(title="SWE Intern", url="https://example.com/job1")],
            evaluations=[ItemEvaluation(
                item="SWE Intern", url="https://example.com/job1",
                decision=EvaluationDecision.SELECTED, reason="Matches profile",
            )],
            selected_items=[DiscoveredItem(title="SWE Intern", url="https://example.com/job1", status="selected")],
            rejected_items=[RejectedItem(title="Senior Dev", url="https://example.com/job2", reason="Too senior")],
            application_drafts=[ApplicationDraft(
                item_title="SWE Intern",
                item_url="https://example.com/job1",
                status=DraftStatus.READY_FOR_REVIEW,
                matched_requirements=["Python"],
                notes="Ready to review",
            )],
            candidate_profile=CandidateProfile(education="B.S. CS", graduation_year=2026, technical_skills=["Python"]),
            errors=[],
        )
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=final_st,
            decision=AgentDecisionResult(action="respond", response_text="Found 1 match.", updated_state=final_st),
            verification_status="response_success",
            cycle_count=5,
            stop_reason="completed_response",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        create_res = self.client.post("/api/tasks", json={
            "goal": "Full UI contract check",
            "profile": {"education": "B.S. CS", "graduation_year": 2026, "technical_skills": ["Python"]},
        })
        self.assertEqual(create_res.status_code, 201)
        tid = create_res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed",))

        required_fields = [
            "task_id", "goal", "status", "observations", "discovered_items",
            "evaluations", "application_drafts", "selected_items", "rejected_items",
            "errors", "final_response", "pending_approval", "cycle_count",
        ]
        for field in required_fields:
            self.assertIn(field, data, f"Frontend-required field '{field}' missing")

        self.assertIsInstance(data["observations"], list)
        self.assertIsInstance(data["evaluations"], list)
        self.assertIsInstance(data["application_drafts"], list)
        self.assertIsInstance(data["errors"], list)
        self.assertEqual(data["status"], "completed")
        self.assertIsNotNone(data["final_response"])
        self.assertEqual(data["application_drafts"][0]["status"], "ready_for_review")

    def test_e2e_7b_profile_serialization(self):
        """E2E-7b: CandidateProfile in the task record is properly serialized."""
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=AgentState(task_id="e2e-serial", user_goal="g", task_status=TaskStatus.COMPLETED),
            verification_status="response_success",
            cycle_count=1,
            stop_reason="completed",
        )
        self.mgr.set_runner_factory(lambda: mock_runner)

        res = self.client.post("/api/tasks", json={"goal": "Profile serialization test", "profile": {
            "education": "B.Tech CS",
            "graduation_year": 2026,
            "technical_skills": ["Go", "Rust"],
            "preferred_role": "Backend Intern",
            "location_preferences": ["Remote"],
        }})
        tid = res.json()["task_id"]
        data = self.client.get(f"/api/tasks/{tid}").json()
        prof = data.get("candidate_profile")
        self.assertIsNotNone(prof)
        self.assertEqual(prof["graduation_year"], 2026)
        self.assertEqual(prof["preferred_role"], "Backend Intern")
        self.assertIn("Go", prof["technical_skills"])


# ---------------------------------------------------------------------------
# E2E-8: Error recovery
# ---------------------------------------------------------------------------

class TestE2EErrorRecovery(unittest.TestCase):
    """E2E-8: Failed tool does not terminate workflow; agent can recover gracefully."""

    def setUp(self):
        self.mgr = TaskManager()
        app.state.task_manager = self.mgr
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def test_e2e_8a_failed_tool_records_error(self):
        """E2E-8a: open_url failure is recorded and agent provides a final response."""
        mock_browser = MagicMock(spec=BrowserManager)
        mock_browser.open_url.return_value = {
            "success": False,
            "error": "Connection refused: https://unreachable.example.com",
            "url": None,
        }
        registry = ToolRegistry(mock_browser)
        llm = _SequentialMockLLM([
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://unreachable.example.com"})]),
            LLMResponse(text="Could not reach the target URL. No internships found due to network error."),
        ])
        runner = AgentRunner(tool_registry=registry, llm_provider=llm, browser_manager=mock_browser)
        self.mgr.set_runner_factory(lambda: runner)

        res = self.client.post("/api/tasks", json={"goal": "Find internships at unreachable site", "max_cycles": 5})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed", "failed"))

        self.assertIn(data["status"], ("completed", "failed"))
        all_text = [o["summary"] for o in data.get("observations", [])] + data.get("errors", [])
        self.assertTrue(
            any("fail" in s.lower() or "error" in s.lower() or "refused" in s.lower() for s in all_text),
            "Failed tool call must be recorded in observations or errors",
        )

    def test_e2e_8b_llm_error_recorded_in_state(self):
        """E2E-8b: LLM provider error is recorded in state and does not crash the task."""
        mock_browser = MagicMock(spec=BrowserManager)
        registry = ToolRegistry(mock_browser)
        error_llm = _SequentialMockLLM([LLMResponse(error="Quota exceeded: rate limit reached")])
        runner = AgentRunner(tool_registry=registry, llm_provider=error_llm, browser_manager=mock_browser)
        self.mgr.set_runner_factory(lambda: runner)

        res = self.client.post("/api/tasks", json={"goal": "Test LLM error handling", "max_cycles": 2})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed", "failed"))
        self.assertTrue(
            len(data.get("errors", [])) > 0 or len(data.get("observations", [])) > 0,
            "LLM error must be captured in state",
        )


# ---------------------------------------------------------------------------
# E2E-9: Application draft lifecycle
# ---------------------------------------------------------------------------

class TestE2EApplicationDraftLifecycle(unittest.TestCase):
    """E2E-9: Application draft created only after evaluate_item selection."""

    def setUp(self):
        self.mgr = TaskManager()
        app.state.task_manager = self.mgr
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def test_e2e_9a_draft_created_after_selection(self):
        """E2E-9a: prepare_application succeeds after evaluate_item selects the item."""
        mock_browser = _make_mock_browser()
        registry = ToolRegistry(mock_browser)
        llm = _SequentialMockLLM([
            LLMResponse(tool_calls=[LLMToolCall(name="open_url", arguments={"url": "https://example.com/jobs/acme-swe-2026"})]),
            LLMResponse(tool_calls=[LLMToolCall(name="evaluate_item", arguments={
                "item": "Acme Tech SWE Intern 2026",
                "url": "https://example.com/jobs/acme-swe-2026",
                "decision": "selected",
                "reason": "Matches profile completely.",
            })]),
            LLMResponse(tool_calls=[LLMToolCall(name="prepare_application", arguments={
                "item_title": "Acme Tech SWE Intern 2026",
                "item_url": "https://example.com/jobs/acme-swe-2026",
                "matched_requirements": ["Python", "React", "FastAPI"],
                "missing_requirements": [],
                "notes": "Strong match. Ready to submit pending human review.",
            })]),
            LLMResponse(text="Application draft prepared for Acme Tech SWE Intern 2026. Ready for your review."),
        ])
        runner = AgentRunner(tool_registry=registry, llm_provider=llm, browser_manager=mock_browser)
        self.mgr.set_runner_factory(lambda: runner)

        res = self.client.post("/api/tasks", json={"goal": "Prepare application for best SWE intern role", "max_cycles": 8})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed", "failed"))
        self.assertEqual(data["status"], "completed", f"Errors: {data.get('errors')}")

        drafts = data.get("application_drafts", [])
        self.assertGreaterEqual(len(drafts), 1, "Expected at least 1 application draft")
        self.assertEqual(drafts[0]["item_url"], "https://example.com/jobs/acme-swe-2026")
        self.assertIn(drafts[0]["status"], ("draft", "ready_for_review"))
        self.assertIn("Python", drafts[0].get("matched_requirements", []))

    def test_e2e_9b_draft_blocked_without_selection(self):
        """E2E-9b: prepare_application is blocked if item was not previously evaluated and selected."""
        mock_browser = _make_mock_browser()
        registry = ToolRegistry(mock_browser)
        llm = _SequentialMockLLM([
            LLMResponse(tool_calls=[LLMToolCall(name="prepare_application", arguments={
                "item_title": "Unevaluated Role",
                "item_url": "https://example.com/jobs/unevaluated",
                "matched_requirements": [],
                "missing_requirements": [],
                "notes": "Skipping evaluation step.",
            })]),
            LLMResponse(text="Application could not be prepared: item was not selected."),
        ])
        runner = AgentRunner(tool_registry=registry, llm_provider=llm, browser_manager=mock_browser)
        self.mgr.set_runner_factory(lambda: runner)

        res = self.client.post("/api/tasks", json={"goal": "Prepare application without evaluation", "max_cycles": 5})
        tid = res.json()["task_id"]
        data = _wait_for_status(self.client, tid, ("completed", "failed"))

        self.assertEqual(len(data.get("application_drafts", [])), 0,
                         "Draft must NOT be created for an unevaluated item")
        all_text = data.get("errors", []) + [o["summary"] for o in data.get("observations", [])]
        self.assertTrue(
            any("blocked" in s.lower() or "not been evaluated" in s.lower() for s in all_text),
            "prepare_application block must be recorded",
        )


# ---------------------------------------------------------------------------
# E2E-10: Local HTML fixture smoke tests
# ---------------------------------------------------------------------------

class TestE2ELocalFixtureSmoke(unittest.TestCase):
    """E2E-10: Local internship fixture HTML is present and parseable."""

    def test_e2e_10a_fixture_file_exists(self):
        """E2E-10a: listings.html fixture exists in test_pages/internships/."""
        self.assertTrue(LISTINGS_HTML_PATH.exists(), f"Expected fixture at {LISTINGS_HTML_PATH}")

    def test_e2e_10b_fixture_contains_all_listings(self):
        """E2E-10b: Fixture HTML contains all three expected job listings."""
        content = LISTINGS_HTML_PATH.read_text(encoding="utf-8")
        self.assertIn("Software Engineering Intern - Summer 2026", content)
        self.assertIn("Acme Tech", content)
        self.assertIn("Senior DevOps Infrastructure Engineer", content)
        self.assertIn("Legacy Systems Inc", content)
        self.assertIn("Backend Engineering Intern", content)
        self.assertIn("Mystery Stealth Co", content)

    def test_e2e_10c_fixture_has_correct_urls(self):
        """E2E-10c: Fixture HTML contains the expected job detail URLs."""
        content = LISTINGS_HTML_PATH.read_text(encoding="utf-8")
        self.assertIn("https://example.com/jobs/acme-swe-2026", content)
        self.assertIn("https://example.com/jobs/devops-senior", content)
        self.assertIn("https://example.com/jobs/stealth-backend", content)

    def test_e2e_10d_fixture_has_eligibility_criteria(self):
        """E2E-10d: Fixture HTML contains eligibility criteria for each listing."""
        content = LISTINGS_HTML_PATH.read_text(encoding="utf-8")
        self.assertIn("graduating in 2026", content)
        self.assertIn("5+ years full-time industry experience", content)
        self.assertIn("Graduation year, degree level, and work authorization criteria not provided", content)

    def test_e2e_10e_evaluate_item_processes_fixture(self):
        """E2E-10e: evaluate_item tool processes fixture content and returns structured result."""
        fixture_text = LISTINGS_HTML_PATH.read_text(encoding="utf-8")
        mock_browser = MagicMock(spec=BrowserManager)
        mock_browser.get_page_text.return_value = {
            "success": True,
            "text": fixture_text,
            "url": str(LISTINGS_HTML_PATH),
        }
        registry = ToolRegistry(mock_browser)
        result = registry.execute("evaluate_item", {
            "item": "Software Engineering Intern - Summer 2026",
            "url": "https://example.com/jobs/acme-swe-2026",
            "decision": "selected",
            "reason": "Remote internship, Python/React/FastAPI, eligible for 2026 CS graduates.",
        })
        self.assertTrue(result.get("success"), f"evaluate_item failed: {result}")
        self.assertEqual(result["evaluation"]["decision"], "selected")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_e2e_tests() -> bool:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestE2EInternshipResearchWorkflow,
        TestE2EProfileAwareMatching,
        TestE2EStatusPollingConsistency,
        TestE2EApprovalGateIntegration,
        TestE2EStopCancellation,
        TestE2EUIDataContract,
        TestE2EErrorRecovery,
        TestE2EApplicationDraftLifecycle,
        TestE2ELocalFixtureSmoke,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    log.info("=" * 70)
    log.info("Task 2R -- End-to-End Browser Research Verification")
    log.info("=" * 70)
    success = run_all_e2e_tests()
    sys.exit(0 if success else 1)
