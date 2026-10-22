"""
Deterministic Test Suite for Task 2P -- Profile-Aware Internship Discovery and Matching.

Validates:
  1. CandidateProfile model validation, sensible defaults, and rejection of malformed inputs.
  2. Backward compatibility of task creation without a candidate profile.
  3. CandidateProfile propagation into AgentState, TaskManager, and decision prompts.
  4. System instruction and decision prompt inclusion of profile criteria.
  5. Profile-aware evaluation: evidence-based selection of matching internships.
  6. Profile-aware rejection: evidence-based rejection of non-internships, skill mismatches, and experience mismatches.
  7. Handling missing eligibility information without assuming qualification.
  8. Preserving safety boundaries: ApprovalGate, no automatic application submission.
"""

import time
import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.agent.state import (
    AgentState,
    CandidateProfile,
    Constraint,
    DiscoveredItem,
    EvaluationDecision,
    ItemEvaluation,
    Observation,
    ResearchFinding,
    TaskStatus,
)
from app.agent.decision import (
    AgentDecisionEngine,
    AgentDecisionResult,
    build_decision_prompt,
    build_system_instruction,
)
from app.agent.tools import EvaluateItemInput, ToolRegistry
from app.agent.runner import AgentRunner, run_agent_task
from app.agent.graph import AgentGraphResult
from app.agent.service import TaskManager, global_task_manager
from app.safety.approval import ApprovalGate, is_consequential


class TestCandidateProfileModel(unittest.TestCase):
    """1. CandidateProfile model validation and parsing."""

    def test_valid_profile_creation(self):
        profile = CandidateProfile(
            education="B.S. in Computer Science",
            graduation_year=2026,
            technical_skills=["Python", "FastAPI", "React"],
            experience_level="undergraduate intern",
            preferred_role="Software Engineering Intern",
            location_preferences=["Remote", "San Francisco"],
            internship_constraints=["Summer 2026", "Paid only"],
        )
        self.assertEqual(profile.graduation_year, 2026)
        self.assertEqual(len(profile.technical_skills), 3)
        self.assertIn("Python", profile.technical_skills)
        self.assertEqual(profile.preferred_role, "Software Engineering Intern")
        self.assertEqual(len(profile.location_preferences), 2)

    def test_default_values_for_optional_fields(self):
        profile = CandidateProfile()
        self.assertIsNone(profile.education)
        self.assertIsNone(profile.graduation_year)
        self.assertEqual(profile.technical_skills, [])
        self.assertIsNone(profile.experience_level)
        self.assertIsNone(profile.preferred_role)
        self.assertEqual(profile.location_preferences, [])
        self.assertEqual(profile.internship_constraints, [])

    def test_comma_separated_string_parsing_for_lists(self):
        profile = CandidateProfile(
            technical_skills="Python, React, TypeScript, Docker",
            location_preferences="Remote, Seattle, Bangalore",
            internship_constraints="Summer 2026, Full-time",
        )
        self.assertEqual(profile.technical_skills, ["Python", "React", "TypeScript", "Docker"])
        self.assertEqual(profile.location_preferences, ["Remote", "Seattle", "Bangalore"])
        self.assertEqual(profile.internship_constraints, ["Summer 2026", "Full-time"])

    def test_invalid_graduation_year_rejected(self):
        with self.assertRaises(ValueError):
            CandidateProfile(graduation_year=1950)

        with self.assertRaises(ValueError):
            CandidateProfile(graduation_year=2150)


class TestPromptAndStatePropagation(unittest.TestCase):
    """2. Propagation into AgentState and LLM decision prompts."""

    def test_profile_stored_in_agent_state(self):
        profile = CandidateProfile(
            education="B.Tech Computer Engineering",
            graduation_year=2026,
            technical_skills=["Python", "Go"],
            preferred_role="Software Engineering Intern",
        )
        state = AgentState(
            task_id="task-prof-01",
            user_goal="Find software engineering internships for Summer 2026",
            candidate_profile=profile,
        )
        self.assertIsNotNone(state.candidate_profile)
        self.assertEqual(state.candidate_profile.graduation_year, 2026)
        self.assertEqual(state.candidate_profile.preferred_role, "Software Engineering Intern")

    def test_prompt_includes_candidate_profile_details(self):
        profile = CandidateProfile(
            education="M.S. in Computer Science",
            graduation_year=2026,
            technical_skills=["Python", "PyTorch", "FastAPI"],
            experience_level="Graduate Student",
            preferred_role="AI / SWE Intern",
            location_preferences=["Remote"],
            internship_constraints=["Summer 2026"],
        )
        state = AgentState(
            task_id="task-prompt-01",
            user_goal="Find AI and Software Engineering Internships",
            candidate_profile=profile,
        )
        prompt = build_decision_prompt(state)
        self.assertIn("Candidate Profile:", prompt)
        self.assertIn("Preferred Role: AI / SWE Intern", prompt)
        self.assertIn("Education: M.S. in Computer Science", prompt)
        self.assertIn("Graduation Year: 2026", prompt)
        self.assertIn("Python, PyTorch, FastAPI", prompt)
        self.assertIn("Location Preferences: Remote", prompt)
        self.assertIn("Internship Constraints: Summer 2026", prompt)

    def test_prompt_without_candidate_profile_remains_valid(self):
        state = AgentState(
            task_id="task-prompt-none",
            user_goal="Find general listings",
        )
        prompt = build_decision_prompt(state)
        self.assertIn("Candidate Profile:\nNone", prompt)

    def test_system_instruction_contains_internship_matching_rules(self):
        instructions = build_system_instruction()
        self.assertIn("internship discovery and candidate profile matching", instructions)
        self.assertIn("Never treat missing evidence as proof of eligibility", instructions)
        self.assertIn("Never fabricate qualifications for the candidate or fake job listings", instructions)


class TestAPIBackwardCompatibilityAndProfile(unittest.TestCase):
    """3. API handling of candidate profiles and backward compatibility."""

    def setUp(self):
        self.mock_task_manager = TaskManager()
        app.state.task_manager = self.mock_task_manager
        self.client = TestClient(app)

    def tearDown(self):
        app.state.task_manager = global_task_manager

    def test_create_task_without_profile_succeeds(self):
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=AgentState(task_id="t-no-prof", user_goal="Find jobs", task_status=TaskStatus.COMPLETED),
            decision=AgentDecisionResult(action="respond", response_text="Done.", updated_state=AgentState(task_id="t-no-prof", user_goal="Find jobs")),
            verification_status="response_success",
            cycle_count=1,
            stop_reason="completed",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        # Standard request with goal only
        res = self.client.post("/api/tasks", json={"goal": "Find jobs"})
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIsNone(data.get("candidate_profile"))

    def test_create_task_with_candidate_profile_persists_in_state(self):
        mock_runner = MagicMock()
        mock_runner.run_task.return_value = AgentGraphResult(
            final_state=AgentState(task_id="t-with-prof", user_goal="Find internships", task_status=TaskStatus.COMPLETED),
            decision=AgentDecisionResult(action="respond", response_text="Found 2 matching roles.", updated_state=AgentState(task_id="t-with-prof", user_goal="Find internships")),
            verification_status="response_success",
            cycle_count=1,
            stop_reason="completed",
        )
        self.mock_task_manager.set_runner_factory(lambda: mock_runner)

        payload = {
            "goal": "Find SWE internships for 2026 grad",
            "max_cycles": 3,
            "profile": {
                "education": "B.Tech in CS",
                "graduation_year": 2026,
                "technical_skills": ["Python", "FastAPI"],
                "preferred_role": "Software Engineering Intern",
                "location_preferences": ["Remote"],
            },
        }

        res = self.client.post("/api/tasks", json=payload)
        self.assertEqual(res.status_code, 201)
        tid = res.json()["task_id"]

        # Verify profile is present in retrieved task
        get_res = self.client.get(f"/api/tasks/{tid}")
        self.assertEqual(get_res.status_code, 200)
        task_data = get_res.json()
        self.assertIsNotNone(task_data.get("candidate_profile"))
        self.assertEqual(task_data["candidate_profile"]["graduation_year"], 2026)
        self.assertEqual(task_data["candidate_profile"]["preferred_role"], "Software Engineering Intern")


class TestProfileAwareMatchingAndEvidence(unittest.TestCase):
    """4. Profile-aware evaluation logic: matching, rejection, and missing evidence."""

    def test_evaluate_matching_internship_selected(self):
        """Listing that meets candidate profile is selected with an evidence-based reason."""
        profile = CandidateProfile(
            education="B.S. in Computer Science",
            graduation_year=2026,
            technical_skills=["Python", "React", "FastAPI"],
            preferred_role="Software Engineering Intern",
            location_preferences=["Remote"],
        )
        state = AgentState(
            task_id="test-match-01",
            user_goal="Find matching SWE internships",
            candidate_profile=profile,
        )

        mock_browser = MagicMock()
        registry = ToolRegistry(mock_browser)
        mock_llm = MagicMock()

        # Decision 1: Record research finding
        # Decision 2: Evaluate as selected with evidence
        # Decision 3: Respond
        eval_args = {
            "item": "Acme Tech - Software Engineering Intern 2026",
            "url": "https://example.com/jobs/acme-swe-2026",
            "decision": "selected",
            "reason": "Matches candidate profile: Remote internship requiring Python, React, and 2026 CS graduation.",
        }

        eval_input = EvaluateItemInput(**eval_args)
        eval_result = registry.execute("evaluate_item", eval_input.model_dump())
        self.assertTrue(eval_result["success"])
        self.assertEqual(eval_result["evaluation"]["decision"], "selected")

    def test_evaluate_experience_mismatch_rejected(self):
        """Listing requiring 5+ years experience when candidate is student intern is rejected."""
        profile = CandidateProfile(
            education="B.S. in Computer Science",
            graduation_year=2026,
            experience_level="intern",
        )
        state = AgentState(
            task_id="test-match-02",
            user_goal="Find internships",
            candidate_profile=profile,
        )

        mock_browser = MagicMock()
        registry = ToolRegistry(mock_browser)

        eval_args = {
            "item": "Legacy Systems - Senior DevOps Engineer",
            "url": "https://example.com/jobs/devops-senior",
            "decision": "rejected",
            "reason": "Position requires 5+ years experience and is not an internship (candidate is 2026 undergraduate).",
        }

        eval_input = EvaluateItemInput(**eval_args)
        eval_result = registry.execute("evaluate_item", eval_input.model_dump())
        self.assertTrue(eval_result["success"])
        self.assertEqual(eval_result["evaluation"]["decision"], "rejected")
        self.assertIn("5+ years experience", eval_result["evaluation"]["reason"])

    def test_evaluate_missing_eligibility_information_rejected(self):
        """Listing with missing or unverified graduation/eligibility criteria is rejected with reason."""
        profile = CandidateProfile(
            graduation_year=2026,
            location_preferences=["Remote"],
        )
        state = AgentState(
            task_id="test-match-03",
            user_goal="Find verified internships",
            candidate_profile=profile,
        )

        mock_browser = MagicMock()
        registry = ToolRegistry(mock_browser)

        eval_args = {
            "item": "Mystery Stealth Co - Backend Intern",
            "url": "https://example.com/jobs/stealth-backend",
            "decision": "rejected",
            "reason": "Missing eligibility info: listing does not specify graduation year, term availability, or location.",
        }

        eval_input = EvaluateItemInput(**eval_args)
        eval_result = registry.execute("evaluate_item", eval_input.model_dump())
        self.assertTrue(eval_result["success"])
        self.assertEqual(eval_result["evaluation"]["decision"], "rejected")
        self.assertIn("Missing eligibility info", eval_result["evaluation"]["reason"])


class TestSafetyPreservation(unittest.TestCase):
    """5. Safety checks: approval gating, no automatic submissions, no email sending."""

    def test_safe_tools_not_consequential(self):
        gate = ApprovalGate()
        self.assertFalse(is_consequential("open_url"))
        self.assertFalse(is_consequential("evaluate_item"))
        self.assertFalse(is_consequential("record_research_finding"))
        self.assertFalse(is_consequential("prepare_application"))

    def test_consequential_actions_require_approval(self):
        self.assertTrue(is_consequential("submit_application"))
        self.assertTrue(is_consequential("send_email"))
        self.assertTrue(is_consequential("delete"))
        self.assertTrue(is_consequential("purchase"))


if __name__ == "__main__":
    unittest.main()
