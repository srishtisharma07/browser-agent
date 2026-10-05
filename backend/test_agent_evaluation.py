"""
Tests for Task 2M -- Structured Relevance, Selection & Rejection.

Validates:
  1. ItemEvaluation model accepts 'selected' and 'rejected' decisions.
  2. evaluate_item tool is registered in ToolRegistry.
  3. evaluate_item tool returns success dict with evaluation payload.
  4. AgentDecisionEngine persists evaluations into AgentState.evaluations.
  5. Selected items are mirrored into AgentState.selected_items.
  6. Rejected items are mirrored into AgentState.rejected_items.
  7. EvaluationDecision enum is strictly 'selected' or 'rejected'.
"""

import unittest
from unittest.mock import MagicMock

from app.agent.state import (
    AgentState,
    EvaluationDecision,
    ItemEvaluation,
    TaskStatus,
)
from app.agent.tools import EvaluateItemInput, ToolRegistry
from app.agent.decision import AgentDecisionEngine
from app.llm.provider import LLMResponse, LLMToolCall as ToolCall


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_state(**kwargs) -> AgentState:
    defaults = {"task_id": "test-eval-001", "user_goal": "Evaluate items"}
    defaults.update(kwargs)
    return AgentState(**defaults)


def _make_registry() -> ToolRegistry:
    """Returns a ToolRegistry backed by a minimal BrowserManager mock."""
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


# ---------------------------------------------------------------------------
# 1. ItemEvaluation model
# ---------------------------------------------------------------------------

class TestItemEvaluationModel(unittest.TestCase):

    def test_selected_decision(self):
        ev = ItemEvaluation(
            item="Example Page",
            url="https://example.com",
            decision=EvaluationDecision.SELECTED,
            reason="Contains directly relevant information.",
        )
        self.assertEqual(ev.decision, EvaluationDecision.SELECTED)
        self.assertEqual(ev.decision.value, "selected")

    def test_rejected_decision(self):
        ev = ItemEvaluation(
            item="Ad Page",
            url="https://ads.example.com",
            decision=EvaluationDecision.REJECTED,
            reason="Contains only advertisements, no useful content.",
        )
        self.assertEqual(ev.decision, EvaluationDecision.REJECTED)
        self.assertEqual(ev.decision.value, "rejected")

    def test_string_coercion_selected(self):
        ev = ItemEvaluation(
            item="Test",
            url="https://test.com",
            decision="selected",
            reason="ok",
        )
        self.assertEqual(ev.decision, EvaluationDecision.SELECTED)

    def test_string_coercion_rejected(self):
        ev = ItemEvaluation(
            item="Test",
            url="https://test.com",
            decision="rejected",
            reason="not relevant",
        )
        self.assertEqual(ev.decision, EvaluationDecision.REJECTED)

    def test_invalid_decision_raises(self):
        with self.assertRaises(Exception):
            ItemEvaluation(
                item="Test",
                url="https://test.com",
                decision="maybe",
                reason="undecided",
            )

    def test_required_fields(self):
        with self.assertRaises(Exception):
            ItemEvaluation(url="https://test.com", decision="selected", reason="ok")


# ---------------------------------------------------------------------------
# 2. EvaluateItemInput schema
# ---------------------------------------------------------------------------

class TestEvaluateItemInput(unittest.TestCase):

    def test_valid_selected(self):
        inp = EvaluateItemInput(
            item="Docs Page",
            url="https://docs.example.com",
            decision="selected",
            reason="Official documentation, highly relevant.",
        )
        self.assertEqual(inp.decision, "selected")

    def test_valid_rejected(self):
        inp = EvaluateItemInput(
            item="Login Page",
            url="https://example.com/login",
            decision="rejected",
            reason="Authentication wall; no content accessible.",
        )
        self.assertEqual(inp.decision, "rejected")

    def test_invalid_decision_literal(self):
        with self.assertRaises(Exception):
            EvaluateItemInput(
                item="Test",
                url="https://test.com",
                decision="pending",
                reason="n/a",
            )


# ---------------------------------------------------------------------------
# 3. ToolRegistry: evaluate_item registered and executable
# ---------------------------------------------------------------------------

class TestEvaluateItemToolRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = _make_registry()

    def test_tool_registered(self):
        self.assertTrue(self.registry.has("evaluate_item"))

    def test_tool_in_list(self):
        self.assertIn("evaluate_item", self.registry.list_tools())

    def test_tool_schema_present(self):
        schemas = self.registry.get_tool_schemas()
        names = [s["name"] for s in schemas]
        self.assertIn("evaluate_item", names)

    def test_execute_selected(self):
        result = self.registry.execute("evaluate_item", {
            "item": "Homepage",
            "url": "https://example.com",
            "decision": "selected",
            "reason": "Direct match.",
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["evaluation"]["decision"], "selected")

    def test_execute_rejected(self):
        result = self.registry.execute("evaluate_item", {
            "item": "Contact Page",
            "url": "https://example.com/contact",
            "decision": "rejected",
            "reason": "No relevant content.",
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["evaluation"]["decision"], "rejected")

    def test_execute_invalid_args(self):
        result = self.registry.execute("evaluate_item", {
            "item": "Test",
            "decision": "selected",
            "reason": "ok",
        })
        self.assertFalse(result["success"])
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# 4, 5, 6. Decision engine persists evaluations and mirrors into lists
# ---------------------------------------------------------------------------

class TestDecisionEngineEvaluateItem(unittest.TestCase):

    def _engine_with_mock_llm(self, tool_name, arguments):
        registry = _make_registry()
        mock_llm = MagicMock()
        mock_llm.generate.return_value = LLMResponse(
            text=None,
            tool_calls=[ToolCall(name=tool_name, arguments=arguments)],
        )
        return AgentDecisionEngine(tool_registry=registry, llm_provider=mock_llm)

    def test_selected_persisted_in_evaluations(self):
        engine = self._engine_with_mock_llm("evaluate_item", {
            "item": "Research Page",
            "url": "https://example.com/research",
            "decision": "selected",
            "reason": "Rich academic content.",
        })
        result = engine.execute_cycle(_make_state())
        self.assertEqual(len(result.updated_state.evaluations), 1)
        ev = result.updated_state.evaluations[0]
        self.assertEqual(ev.decision, EvaluationDecision.SELECTED)
        self.assertEqual(ev.item, "Research Page")

    def test_selected_mirrored_to_selected_items(self):
        engine = self._engine_with_mock_llm("evaluate_item", {
            "item": "Research Page",
            "url": "https://example.com/research",
            "decision": "selected",
            "reason": "Rich academic content.",
        })
        result = engine.execute_cycle(_make_state())
        self.assertEqual(len(result.updated_state.selected_items), 1)
        self.assertEqual(result.updated_state.selected_items[0].url, "https://example.com/research")
        self.assertEqual(result.updated_state.selected_items[0].status, "selected")
        self.assertEqual(len(result.updated_state.rejected_items), 0)

    def test_rejected_persisted_in_evaluations(self):
        engine = self._engine_with_mock_llm("evaluate_item", {
            "item": "Ad Page",
            "url": "https://ads.example.com",
            "decision": "rejected",
            "reason": "Only advertisements.",
        })
        result = engine.execute_cycle(_make_state())
        self.assertEqual(len(result.updated_state.evaluations), 1)
        ev = result.updated_state.evaluations[0]
        self.assertEqual(ev.decision, EvaluationDecision.REJECTED)
        self.assertEqual(ev.reason, "Only advertisements.")

    def test_rejected_mirrored_to_rejected_items(self):
        engine = self._engine_with_mock_llm("evaluate_item", {
            "item": "Ad Page",
            "url": "https://ads.example.com",
            "decision": "rejected",
            "reason": "Only advertisements.",
        })
        result = engine.execute_cycle(_make_state())
        self.assertEqual(len(result.updated_state.rejected_items), 1)
        r = result.updated_state.rejected_items[0]
        self.assertEqual(r.url, "https://ads.example.com")
        self.assertEqual(r.reason, "Only advertisements.")
        self.assertEqual(len(result.updated_state.selected_items), 0)

    def test_multiple_evaluations_accumulate(self):
        registry = _make_registry()
        mock_llm = MagicMock()
        mock_llm.generate.side_effect = [
            LLMResponse(text=None, tool_calls=[ToolCall(name="evaluate_item", arguments={
                "item": "Page A", "url": "https://example.com/a",
                "decision": "selected", "reason": "Good content.",
            })]),
            LLMResponse(text=None, tool_calls=[ToolCall(name="evaluate_item", arguments={
                "item": "Page B", "url": "https://example.com/b",
                "decision": "rejected", "reason": "Off-topic.",
            })]),
        ]
        engine = AgentDecisionEngine(tool_registry=registry, llm_provider=mock_llm)
        state = _make_state()
        state = engine.execute_cycle(state).updated_state
        state = engine.execute_cycle(state).updated_state
        self.assertEqual(len(state.evaluations), 2)
        self.assertEqual(len(state.selected_items), 1)
        self.assertEqual(len(state.rejected_items), 1)


# ---------------------------------------------------------------------------
# 7. EvaluationDecision enum coverage
# ---------------------------------------------------------------------------

class TestEvaluationDecisionEnum(unittest.TestCase):

    def test_enum_values(self):
        values = {e.value for e in EvaluationDecision}
        self.assertEqual(values, {"selected", "rejected"})

    def test_enum_is_str_subclass(self):
        self.assertIsInstance(EvaluationDecision.SELECTED, str)
        self.assertIsInstance(EvaluationDecision.REJECTED, str)


if __name__ == "__main__":
    unittest.main()
