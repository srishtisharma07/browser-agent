"""
test_application_preparation.py � Verification test suite for Task 2N:
Application Preparation State.

Run from backend/ directory:

    .venv\Scripts\python -m pytest test_application_preparation.py -v
    # or
    .venv\Scripts\python test_application_preparation.py

Tests verified:
 1. ApplicationDraft model validation: required fields, valid HTTP/HTTPS URLs.
 2. PrepareApplicationInput tool registration and Pydantic input validation.
 3. Successful draft creation and persistence in AgentState.application_drafts.
 4. Draft status is set to ready_for_review after prepare_application.
 5. Unselected items are rejected with a structured failure.
 6. An item already in evaluations as 'selected' permits draft preparation.
 7. Blank required fields (item_title, item_url) are rejected.
 8. prepare_application does NOT itself require consequential-action approval.
 9. Existing consequential actions (submit_application) still require approval.
10. Existing research and evaluation workflows remain functional.
"""

import unittest
from unittest.mock import MagicMock

import sys
sys.path.insert(0, ".")

from pydantic import ValidationError

from app.agent.state import (
    AgentState,
    ApplicationDraft,
    DiscoveredItem,
    DraftStatus,
    EvaluationDecision,
    ItemEvaluation,
    TaskStatus,
)
from app.agent.tools import PrepareApplicationInput, ToolRegistry
from app.agent.decision import AgentDecisionEngine, build_decision_prompt
from app.llm.provider import LLMResponse, LLMToolCall as ToolCall
from app.safety.approval import is_consequential, SAFE_BROWSER_TOOLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**kwargs) -> AgentState:
    defaults = {"task_id": "test-2n-001", "user_goal": "Prepare applications for selected jobs"}
    defaults.update(kwargs)
    return AgentState(**defaults)


def _make_registry() -> ToolRegistry:
    """ToolRegistry backed by a minimal BrowserManager mock."""
    mock_browser = MagicMock()
    mock_browser.open_url.return_value = {"success": True, "url": "https://example.com"}
    mock_browser.get_page_text.return_value = {"success": True, "text": "page text"}
    mock_browser.get_links.return_value = {"success": True, "links": []}
    mock_browser.click.return_value = {"success": True}
    mock_browser.fill.return_value = {"success": True}
    mock_browser.press.return_value = {"success": True}
    mock_browser.screenshot.return_value = {"success": True}
    mock_browser.scroll.return_value = {"success": True}
    mock_browser.go_back.return_value = {"success": True}
    return ToolRegistry(browser_manager=mock_browser)


def _engine_with_mock_llm(tool_name: str, arguments: dict) -> AgentDecisionEngine:
    registry = _make_registry()
    mock_llm = MagicMock()
    mock_llm.generate.return_value = LLMResponse(
        text=None,
        tool_calls=[ToolCall(name=tool_name, arguments=arguments)],
    )
    return AgentDecisionEngine(tool_registry=registry, llm_provider=mock_llm)


def _selected_state(item_url: str, item_title: str = "Selected Job") -> AgentState:
    """Returns a state where item_url is already evaluated and selected."""
    state = _make_state()
    state.evaluations.append(ItemEvaluation(
        item=item_title,
        url=item_url,
        decision=EvaluationDecision.SELECTED,
        reason="Matches all criteria.",
    ))
    state.selected_items.append(DiscoveredItem(
        title=item_title,
        url=item_url,
        status="selected",
    ))
    return state


# ---------------------------------------------------------------------------
# Test 1: ApplicationDraft model and URL validation
# ---------------------------------------------------------------------------

class TestApplicationDraftModel(unittest.TestCase):

    def test_valid_http_url(self):
        draft = ApplicationDraft(
            item_title="Software Engineer Role",
            item_url="http://jobs.example.com/se",
        )
        self.assertEqual(draft.item_url, "http://jobs.example.com/se")
        self.assertEqual(draft.status, DraftStatus.DRAFT)

    def test_valid_https_url(self):
        draft = ApplicationDraft(
            item_title="Data Scientist Role",
            item_url="https://jobs.example.com/ds",
        )
        self.assertEqual(draft.item_url, "https://jobs.example.com/ds")

    def test_invalid_ftp_url_rejected(self):
        with self.assertRaises(ValidationError):
            ApplicationDraft(
                item_title="Some Role",
                item_url="ftp://jobs.example.com/role",
            )

    def test_invalid_local_path_rejected(self):
        with self.assertRaises(ValidationError):
            ApplicationDraft(
                item_title="Some Role",
                item_url="file:///C:/jobs/role.html",
            )

    def test_invalid_no_scheme_rejected(self):
        with self.assertRaises(ValidationError):
            ApplicationDraft(
                item_title="Some Role",
                item_url="jobs.example.com/role",
            )

    def test_draft_status_enum_values(self):
        self.assertEqual(DraftStatus.DRAFT.value, "draft")
        self.assertEqual(DraftStatus.READY_FOR_REVIEW.value, "ready_for_review")

    def test_matched_and_missing_requirements_default_empty(self):
        draft = ApplicationDraft(
            item_title="Engineering Role",
            item_url="https://example.com/eng",
        )
        self.assertEqual(draft.matched_requirements, [])
        self.assertEqual(draft.missing_requirements, [])
        self.assertEqual(draft.notes, "")

    def test_full_draft_model(self):
        draft = ApplicationDraft(
            item_title="ML Engineer",
            item_url="https://ml.example.com/jobs/1",
            status=DraftStatus.READY_FOR_REVIEW,
            matched_requirements=["Python", "TensorFlow"],
            missing_requirements=["5+ years exp"],
            notes="Strong candidate, apply soon.",
        )
        self.assertEqual(draft.status, DraftStatus.READY_FOR_REVIEW)
        self.assertIn("Python", draft.matched_requirements)
        self.assertIn("5+ years exp", draft.missing_requirements)

    def test_application_drafts_list_in_agent_state(self):
        state = _make_state()
        self.assertIsInstance(state.application_drafts, list)
        self.assertEqual(len(state.application_drafts), 0)

    def test_state_drafts_do_not_share_mutable_state(self):
        state_a = _make_state()
        state_b = _make_state()
        state_a.application_drafts.append(ApplicationDraft(
            item_title="Role A",
            item_url="https://example.com/a",
        ))
        self.assertEqual(len(state_b.application_drafts), 0)


# ---------------------------------------------------------------------------
# Test 2: Tool registration and PrepareApplicationInput validation
# ---------------------------------------------------------------------------

class TestPrepareApplicationToolRegistration(unittest.TestCase):

    def setUp(self):
        self.registry = _make_registry()

    def test_tool_is_registered(self):
        self.assertTrue(self.registry.has("prepare_application"))

    def test_tool_in_list_tools(self):
        self.assertIn("prepare_application", self.registry.list_tools())

    def test_tool_schema_present_in_schemas(self):
        schemas = self.registry.get_tool_schemas()
        names = [s["name"] for s in schemas]
        self.assertIn("prepare_application", names)

    def test_valid_input_schema_accepted(self):
        inp = PrepareApplicationInput(
            item_title="DevOps Engineer",
            item_url="https://example.com/devops",
            matched_requirements=["CI/CD", "Kubernetes"],
            missing_requirements=["AWS certification"],
            notes="Good fit for role.",
        )
        self.assertEqual(inp.item_title, "DevOps Engineer")
        self.assertEqual(inp.item_url, "https://example.com/devops")

    def test_missing_item_title_raises(self):
        with self.assertRaises(ValidationError):
            PrepareApplicationInput(item_url="https://example.com/job")

    def test_missing_item_url_raises(self):
        with self.assertRaises(ValidationError):
            PrepareApplicationInput(item_title="Engineer")

    def test_tool_execute_returns_success_dict(self):
        result = self.registry.execute("prepare_application", {
            "item_title": "Backend Dev",
            "item_url": "https://jobs.example.com/backend",
            "matched_requirements": ["Python"],
            "missing_requirements": [],
            "notes": "Good fit.",
        })
        self.assertTrue(result["success"])
        self.assertIn("draft", result)

    def test_tool_execute_invalid_args_returns_failure(self):
        result = self.registry.execute("prepare_application", {
            "item_url": "https://example.com/job",
            # missing item_title
        })
        self.assertFalse(result["success"])
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Test 3: Successful draft creation and persistence
# ---------------------------------------------------------------------------

class TestDraftCreationAndPersistence(unittest.TestCase):

    def test_draft_persisted_in_application_drafts(self):
        item_url = "https://example.com/job/python-dev"
        state = _selected_state(item_url, "Python Dev Role")

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Python Dev Role",
            "item_url": item_url,
            "matched_requirements": ["Python", "Django"],
            "missing_requirements": ["5 years exp"],
            "notes": "Good match.",
        })
        result = engine.execute_cycle(state)

        self.assertEqual(len(result.updated_state.application_drafts), 1)
        draft = result.updated_state.application_drafts[0]
        self.assertEqual(draft.item_title, "Python Dev Role")
        self.assertEqual(draft.item_url, item_url)
        self.assertIn("Python", draft.matched_requirements)
        self.assertIn("5 years exp", draft.missing_requirements)
        self.assertEqual(draft.notes, "Good match.")

    def test_observation_added_for_successful_draft(self):
        item_url = "https://example.com/job/ml-engineer"
        state = _selected_state(item_url, "ML Engineer")

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "ML Engineer",
            "item_url": item_url,
            "matched_requirements": ["TensorFlow"],
            "missing_requirements": [],
            "notes": "",
        })
        result = engine.execute_cycle(state)

        draft_obs = [
            o for o in result.updated_state.observations
            if "ready_for_review" in o.summary.lower() or "ready_for_review" in str(o.metadata)
        ]
        self.assertGreater(len(draft_obs), 0,
                           "Expected a ready_for_review observation to be recorded")

    def test_multiple_drafts_accumulate(self):
        item_url_1 = "https://example.com/job/1"
        item_url_2 = "https://example.com/job/2"

        state = _make_state()
        state.evaluations.append(ItemEvaluation(
            item="Job 1", url=item_url_1,
            decision=EvaluationDecision.SELECTED, reason="Good fit"
        ))
        state.evaluations.append(ItemEvaluation(
            item="Job 2", url=item_url_2,
            decision=EvaluationDecision.SELECTED, reason="Also good"
        ))
        state.selected_items.append(DiscoveredItem(title="Job 1", url=item_url_1, status="selected"))
        state.selected_items.append(DiscoveredItem(title="Job 2", url=item_url_2, status="selected"))

        registry = _make_registry()
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = [
            LLMResponse(tool_calls=[ToolCall(name="prepare_application", arguments={
                "item_title": "Job 1",
                "item_url": item_url_1,
            })]),
            LLMResponse(tool_calls=[ToolCall(name="prepare_application", arguments={
                "item_title": "Job 2",
                "item_url": item_url_2,
            })]),
        ]
        engine = AgentDecisionEngine(tool_registry=registry, llm_provider=mock_llm)

        state = engine.execute_cycle(state).updated_state
        state = engine.execute_cycle(state).updated_state

        self.assertEqual(len(state.application_drafts), 2)


# ---------------------------------------------------------------------------
# Test 4: Draft status becomes ready_for_review
# ---------------------------------------------------------------------------

class TestDraftStatusReadyForReview(unittest.TestCase):

    def test_status_is_ready_for_review(self):
        item_url = "https://example.com/job/ready-review"
        state = _selected_state(item_url, "Ready Review Job")

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Ready Review Job",
            "item_url": item_url,
        })
        result = engine.execute_cycle(state)

        self.assertEqual(len(result.updated_state.application_drafts), 1)
        draft = result.updated_state.application_drafts[0]
        self.assertEqual(draft.status, DraftStatus.READY_FOR_REVIEW)

    def test_status_value_string_is_ready_for_review(self):
        item_url = "https://example.com/job/status-check"
        state = _selected_state(item_url, "Status Check Job")

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Status Check Job",
            "item_url": item_url,
        })
        result = engine.execute_cycle(state)

        draft = result.updated_state.application_drafts[0]
        self.assertEqual(draft.status.value, "ready_for_review")

    def test_task_remains_running_after_draft(self):
        item_url = "https://example.com/job/still-running"
        state = _selected_state(item_url, "Still Running Job")
        state.task_status = TaskStatus.RUNNING

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Still Running Job",
            "item_url": item_url,
        })
        result = engine.execute_cycle(state)

        self.assertNotEqual(result.updated_state.task_status, TaskStatus.FAILED)
        self.assertNotEqual(result.updated_state.task_status, TaskStatus.COMPLETED)


# ---------------------------------------------------------------------------
# Test 5: Unselected items are rejected
# ---------------------------------------------------------------------------

class TestUnselectedItemRejected(unittest.TestCase):

    def test_unselected_item_blocked(self):
        state = _make_state()  # No evaluations, no selected_items

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Ghost Job",
            "item_url": "https://example.com/ghost",
        })
        result = engine.execute_cycle(state)

        self.assertEqual(len(result.updated_state.application_drafts), 0)

    def test_unselected_item_records_error(self):
        state = _make_state()

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Ghost Job",
            "item_url": "https://example.com/ghost",
        })
        result = engine.execute_cycle(state)

        error_text = " ".join(result.updated_state.errors)
        self.assertIn("ghost", error_text.lower(),
                      "Expected a blocking error mentioning the item")

    def test_rejected_evaluation_does_not_permit_draft(self):
        state = _make_state()
        state.evaluations.append(ItemEvaluation(
            item="Rejected Job",
            url="https://example.com/rejected-job",
            decision=EvaluationDecision.REJECTED,
            reason="Not a match.",
        ))

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Rejected Job",
            "item_url": "https://example.com/rejected-job",
        })
        result = engine.execute_cycle(state)

        self.assertEqual(len(result.updated_state.application_drafts), 0)

    def test_unselected_failure_does_not_affect_existing_drafts(self):
        item_url_existing = "https://example.com/job/existing"
        state = _selected_state(item_url_existing, "Existing Job")
        state.application_drafts.append(ApplicationDraft(
            item_title="Existing Job",
            item_url=item_url_existing,
            status=DraftStatus.READY_FOR_REVIEW,
        ))

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Ghost Job",
            "item_url": "https://example.com/ghost",
        })
        result = engine.execute_cycle(state)

        self.assertEqual(len(result.updated_state.application_drafts), 1)
        self.assertEqual(result.updated_state.application_drafts[0].item_title, "Existing Job")


# ---------------------------------------------------------------------------
# Test 6: Selected evaluation permits preparation
# ---------------------------------------------------------------------------

class TestSelectedEvaluationPermitsDraft(unittest.TestCase):

    def test_selected_via_evaluations_allows_draft(self):
        item_url = "https://example.com/job/via-eval"
        state = _make_state()
        state.evaluations.append(ItemEvaluation(
            item="Eval Job",
            url=item_url,
            decision=EvaluationDecision.SELECTED,
            reason="Directly matches requirements.",
        ))

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Eval Job",
            "item_url": item_url,
        })
        result = engine.execute_cycle(state)

        self.assertEqual(len(result.updated_state.application_drafts), 1)
        self.assertEqual(result.updated_state.application_drafts[0].status, DraftStatus.READY_FOR_REVIEW)

    def test_selected_via_selected_items_allows_draft(self):
        item_url = "https://example.com/job/via-selected-items"
        state = _make_state()
        state.selected_items.append(DiscoveredItem(
            title="Legacy Selected Job",
            url=item_url,
            status="selected",
        ))

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Legacy Selected Job",
            "item_url": item_url,
        })
        result = engine.execute_cycle(state)

        self.assertEqual(len(result.updated_state.application_drafts), 1)

    def test_both_selected_sources_permit_draft(self):
        item_url = "https://example.com/job/both-sources"
        state = _selected_state(item_url, "Dual Source Job")

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Dual Source Job",
            "item_url": item_url,
        })
        result = engine.execute_cycle(state)

        self.assertEqual(len(result.updated_state.application_drafts), 1)


# ---------------------------------------------------------------------------
# Test 7: Blank required fields are rejected
# ---------------------------------------------------------------------------

class TestBlankRequiredFieldsRejected(unittest.TestCase):

    def test_empty_item_title_rejected_by_model(self):
        with self.assertRaises(ValidationError):
            ApplicationDraft(
                item_title="",
                item_url="https://example.com/job",
            )

    def test_whitespace_only_item_title_rejected(self):
        with self.assertRaises(ValidationError):
            ApplicationDraft(
                item_title="   ",
                item_url="https://example.com/job",
            )

    def test_empty_item_url_rejected_by_model(self):
        with self.assertRaises(ValidationError):
            ApplicationDraft(
                item_title="Some Job",
                item_url="",
            )

    def test_whitespace_only_item_url_rejected(self):
        with self.assertRaises(ValidationError):
            ApplicationDraft(
                item_title="Some Job",
                item_url="   ",
            )

    def test_blank_item_title_in_tool_input_rejected(self):
        with self.assertRaises(ValidationError):
            PrepareApplicationInput(
                item_title="",
                item_url="https://example.com/job",
            )

    def test_blank_item_url_in_tool_input_rejected(self):
        with self.assertRaises(ValidationError):
            PrepareApplicationInput(
                item_title="Some Job",
                item_url="",
            )

    def test_blank_title_via_tool_execute_returns_error(self):
        registry = _make_registry()
        result = registry.execute("prepare_application", {
            "item_title": "",
            "item_url": "https://example.com/job",
        })
        self.assertFalse(result["success"])
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Test 8: prepare_application does NOT require consequential-action approval
# ---------------------------------------------------------------------------

class TestPrepareApplicationNotConsequential(unittest.TestCase):

    def test_prepare_application_not_in_consequential_actions(self):
        self.assertFalse(is_consequential("prepare_application"),
                         "prepare_application must NOT be flagged as consequential")

    def test_prepare_application_gate_does_not_pause(self):
        item_url = "https://example.com/job/no-gate"
        state = _selected_state(item_url, "No Gate Job")

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "No Gate Job",
            "item_url": item_url,
        })
        result = engine.execute_cycle(state)

        self.assertNotEqual(result.updated_state.task_status, TaskStatus.WAITING_FOR_APPROVAL,
                            "prepare_application incorrectly requires approval")
        self.assertIsNone(result.updated_state.pending_approval,
                          "pending_approval should be None for non-consequential prepare_application")

    def test_draft_is_created_without_approval(self):
        item_url = "https://example.com/job/direct"
        state = _selected_state(item_url, "Direct Job")

        engine = _engine_with_mock_llm("prepare_application", {
            "item_title": "Direct Job",
            "item_url": item_url,
        })
        result = engine.execute_cycle(state)

        self.assertEqual(len(result.updated_state.application_drafts), 1)


# ---------------------------------------------------------------------------
# Test 9: Consequential actions still require approval
# ---------------------------------------------------------------------------

class TestConsequentialActionsStillRequireApproval(unittest.TestCase):

    def test_submit_application_is_consequential(self):
        self.assertTrue(is_consequential("submit_application"))

    def test_send_email_is_consequential(self):
        self.assertTrue(is_consequential("send_email"))

    def test_purchase_is_consequential(self):
        self.assertTrue(is_consequential("purchase"))

    def test_delete_is_consequential(self):
        self.assertTrue(is_consequential("delete"))

    def test_submit_application_triggers_approval_gate(self):
        registry = _make_registry()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            tool_calls=[ToolCall(
                name="submit_application",
                arguments={"url": "https://jobs.example.com/apply"}
            )]
        )
        engine = AgentDecisionEngine(tool_registry=registry, llm_provider=mock_llm)
        state = _make_state()
        state.task_status = TaskStatus.RUNNING

        result = engine.execute_cycle(state)

        self.assertEqual(result.updated_state.task_status, TaskStatus.WAITING_FOR_APPROVAL,
                         "submit_application must trigger WAITING_FOR_APPROVAL")
        self.assertIsNotNone(result.updated_state.pending_approval)
        self.assertEqual(result.updated_state.pending_approval.action, "submit_application")

    def test_safe_browser_tools_not_consequential(self):
        for tool in SAFE_BROWSER_TOOLS:
            with self.subTest(tool=tool):
                self.assertFalse(is_consequential(tool),
                                 f"'{tool}' should NOT require approval")


# ---------------------------------------------------------------------------
# Test 10: Existing research and evaluation workflows remain functional
# ---------------------------------------------------------------------------

class TestExistingWorkflowsRemainFunctional(unittest.TestCase):

    def test_record_research_finding_still_works(self):
        registry = _make_registry()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            tool_calls=[ToolCall(name="record_research_finding", arguments={
                "title": "Python Jobs Page",
                "url": "https://jobs.example.com/python",
                "summary": "Lists Python-specific roles with remote options.",
                "key_points": ["Python", "Remote", "Full-time"],
                "source": "browser",
            })]
        )
        engine = AgentDecisionEngine(tool_registry=registry, llm_provider=mock_llm)
        result = engine.execute_cycle(_make_state())

        self.assertEqual(len(result.updated_state.research_findings), 1)
        finding = result.updated_state.research_findings[0]
        self.assertEqual(finding.title, "Python Jobs Page")
        self.assertEqual(finding.source, "browser")

    def test_evaluate_item_selected_still_works(self):
        registry = _make_registry()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            tool_calls=[ToolCall(name="evaluate_item", arguments={
                "item": "Python Developer",
                "url": "https://jobs.example.com/python-dev",
                "decision": "selected",
                "reason": "Direct match for all constraints.",
            })]
        )
        engine = AgentDecisionEngine(tool_registry=registry, llm_provider=mock_llm)
        result = engine.execute_cycle(_make_state())

        self.assertEqual(len(result.updated_state.evaluations), 1)
        self.assertEqual(result.updated_state.evaluations[0].decision, EvaluationDecision.SELECTED)
        self.assertEqual(len(result.updated_state.selected_items), 1)

    def test_evaluate_item_rejected_still_works(self):
        registry = _make_registry()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            tool_calls=[ToolCall(name="evaluate_item", arguments={
                "item": "Java Developer",
                "url": "https://jobs.example.com/java-dev",
                "decision": "rejected",
                "reason": "Wrong language.",
            })]
        )
        engine = AgentDecisionEngine(tool_registry=registry, llm_provider=mock_llm)
        result = engine.execute_cycle(_make_state())

        self.assertEqual(len(result.updated_state.evaluations), 1)
        self.assertEqual(result.updated_state.evaluations[0].decision, EvaluationDecision.REJECTED)
        self.assertEqual(len(result.updated_state.rejected_items), 1)
        self.assertEqual(len(result.updated_state.selected_items), 0)

    def test_application_drafts_appear_in_decision_prompt(self):
        state = _make_state()
        state.application_drafts.append(ApplicationDraft(
            item_title="Python Dev Role",
            item_url="https://example.com/python",
            status=DraftStatus.READY_FOR_REVIEW,
        ))
        prompt = build_decision_prompt(state)
        self.assertIn("Application Drafts", prompt)
        self.assertIn("Python Dev Role", prompt)
        self.assertIn("READY_FOR_REVIEW", prompt)

    def test_evaluations_appear_in_decision_prompt(self):
        state = _make_state()
        state.evaluations.append(ItemEvaluation(
            item="Research Page",
            url="https://example.com/research",
            decision=EvaluationDecision.SELECTED,
            reason="Useful.",
        ))
        prompt = build_decision_prompt(state)
        self.assertIn("Item Evaluations", prompt)
        self.assertIn("Research Page", prompt)

    def test_open_url_still_executes_without_approval(self):
        registry = _make_registry()
        mock_browser = registry._manager
        mock_browser.open_url.return_value = {"success": True, "url": "https://example.com"}
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            tool_calls=[ToolCall(name="open_url", arguments={"url": "https://example.com"})]
        )
        engine = AgentDecisionEngine(tool_registry=registry, llm_provider=mock_llm)
        result = engine.execute_cycle(_make_state())

        self.assertNotEqual(result.updated_state.task_status, TaskStatus.WAITING_FOR_APPROVAL)
        self.assertTrue(mock_browser.open_url.called)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
