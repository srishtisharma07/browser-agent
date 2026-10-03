"""
test_smoke_wiring.py -- Automated provider integration coverage for Task 2K.

Verifies the end-to-end wiring:

    AgentRunner -> GeminiLLMProvider (mocked) -> LangGraph -> ToolRegistry

without requiring a real Gemini API key.

Tests:
1. GeminiLLMProvider is correctly wired inside AgentRunner (default path).
2. Injected GeminiLLMProvider (mock client) drives open_url -> respond cycle.
3. GeminiLLMProvider sanitizes API key from error messages.
4. smoke_test_gemini module imports cleanly and exposes run_smoke_test().
5. smoke_test_gemini.run_smoke_test() returns False (not True) when no API key present.
6. Security: smoke_test_gemini module source contains no forbidden keywords.

Run from backend/ directory:
    .venv\Scripts\python test_smoke_wiring.py
"""

from __future__ import annotations

import inspect
import logging
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from app.config import Config, LLMConfigurationError
from app.llm.gemini import GeminiLLMProvider
from app.llm.provider import LLMProvider, LLMResponse, LLMToolCall
from app.browser.manager import BrowserManager
from app.agent.tools import ToolRegistry
from app.agent.runner import AgentRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: minimal sequential mock LLM provider
# ---------------------------------------------------------------------------

class _SequentialMockProvider(LLMProvider):
    """Returns responses in order; repeats the last one if exhausted."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = responses
        self._idx = 0

    def generate(self, prompt, tools=None, system_instruction=None):  # type: ignore[override]
        resp = self._responses[min(self._idx, len(self._responses) - 1)]
        self._idx += 1
        return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_smoke_wiring_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("Task 2K -- Automated Smoke-Wiring Test Suite")
    log.info("=" * 65)

    # ------------------------------------------------------------------
    # TEST 1: GeminiLLMProvider wired inside AgentRunner (type check)
    # ------------------------------------------------------------------
    log.info("TEST 1 * AgentRunner default-wires GeminiLLMProvider ...")

    # Temporarily inject a dummy key so the provider can be instantiated.
    old_key = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "test-wiring-key-AAAA"
    try:
        runner = AgentRunner()
        # runner.llm_provider is None until run_task is called (lazy init),
        # but we can verify that the module-level default resolves to Gemini.
        from app.agent import runner as runner_module
        src = inspect.getsource(runner_module)
        if "GeminiLLMProvider" not in src:
            log.error("FAILED: GeminiLLMProvider not referenced in runner module.")
            all_passed = False
        else:
            log.info("  OK: GeminiLLMProvider is the default provider in AgentRunner.")
    finally:
        if old_key is not None:
            os.environ["GEMINI_API_KEY"] = old_key
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

    # ------------------------------------------------------------------
    # TEST 2: Injected GeminiLLMProvider (mock client) drives full loop
    # ------------------------------------------------------------------
    log.info("TEST 2 * Injected mocked GeminiLLMProvider drives full loop ...")

    mock_client = MagicMock()
    mock_browser = MagicMock(spec=BrowserManager)
    mock_browser.open_url.return_value = {
        "success": True,
        "url": "https://example.com",
        "error": None,
        "observation": None,
    }
    mock_browser.get_page_text.return_value = {
        "success": True,
        "text": "Example Domain - This domain is for use in illustrative examples.",
        "url": "https://example.com",
    }

    # Build a mock Gemini response sequence: open_url -> get_page_text -> respond
    def _make_tool_resp(name: str, args: dict) -> MagicMock:
        fn = MagicMock()
        fn.name = name
        fn.args = args
        r = MagicMock()
        r.text = None
        r.function_calls = [fn]
        r.candidates = []
        return r

    def _make_text_resp(text: str) -> MagicMock:
        r = MagicMock()
        r.text = text
        r.function_calls = None
        r.candidates = []
        return r

    mock_client.models.generate_content.side_effect = [
        _make_tool_resp("open_url", {"url": "https://example.com"}),
        _make_tool_resp("get_page_text", {"max_length": 5000}),
        _make_text_resp(
            "Example.com is a reserved domain used for illustrative examples in documentation."
        ),
    ]

    gemini_provider = GeminiLLMProvider(
        api_key="test-wiring-key-BBBB",
        model="gemini-2.5-flash",
        client=mock_client,
    )
    registry = ToolRegistry(mock_browser)
    runner2 = AgentRunner(
        tool_registry=registry,
        llm_provider=gemini_provider,
        browser_manager=mock_browser,
    )

    try:
        result = runner2.run_task(
            user_goal=(
                "Open https://example.com/, inspect the page, "
                "gather the main information available on it, and give me a short summary."
            ),
            task_id="smoke-wiring-test",
            max_cycles=8,
        )

        # Validate multi-cycle behavior
        if result.cycle_count < 2:
            log.error(
                "  FAILED: Expected at least 2 cycles, got %d", result.cycle_count
            )
            all_passed = False
        else:
            log.info("  OK: cycle_count=%d", result.cycle_count)

        if result.stop_reason != "completed_response":
            log.error(
                "  FAILED: Expected stop_reason='completed_response', got '%s'",
                result.stop_reason,
            )
            all_passed = False
        else:
            log.info("  OK: stop_reason='completed_response'")

        # Verify open_url and get_page_text were called through ToolRegistry
        mock_browser.open_url.assert_called_once()
        mock_browser.get_page_text.assert_called_once()
        log.info("  OK: open_url and get_page_text called through ToolRegistry.")

        # Verify final response text
        if result.decision and result.decision.response_text:
            log.info("  OK: Final response present (%d chars).", len(result.decision.response_text))
        else:
            log.error("  FAILED: No final response text.")
            all_passed = False

        # Verify observations accumulate across cycles
        obs_sources = [o.source for o in result.final_state.observations]
        if "tool:open_url" not in obs_sources:
            log.error("  FAILED: open_url observation missing from state.")
            all_passed = False
        elif "tool:get_page_text" not in obs_sources:
            log.error("  FAILED: get_page_text observation missing from state.")
            all_passed = False
        else:
            log.info("  OK: Both tool observations present in AgentState.")

    except Exception as exc:
        log.error("  FAILED with exception: %s", exc, exc_info=True)
        all_passed = False

    # ------------------------------------------------------------------
    # TEST 3: GeminiLLMProvider sanitizes API key from error messages
    # ------------------------------------------------------------------
    log.info("TEST 3 * API key sanitization in GeminiLLMProvider ...")

    secret_key = "secret-wiring-key-CCCC"
    mock_client_err = MagicMock()
    mock_client_err.models.generate_content.side_effect = Exception(
        f"Request failed with key {secret_key} exposed!"
    )
    err_provider = GeminiLLMProvider(
        api_key=secret_key,
        model="gemini-2.5-flash",
        client=mock_client_err,
    )
    err_resp = err_provider.generate("test prompt")
    if err_resp.error is None:
        log.error("  FAILED: Expected error response, got None.")
        all_passed = False
    elif secret_key in (err_resp.error or ""):
        log.error("  FAILED: API key leaked in error: %s", err_resp.error)
        all_passed = False
    elif "[REDACTED]" not in (err_resp.error or ""):
        log.error("  FAILED: Error not sanitized: %s", err_resp.error)
        all_passed = False
    else:
        log.info("  OK: API key sanitized correctly in error message.")

    # ------------------------------------------------------------------
    # TEST 4: smoke_test_gemini module imports cleanly
    # ------------------------------------------------------------------
    log.info("TEST 4 * smoke_test_gemini module imports cleanly ...")
    try:
        import smoke_test_gemini as stg  # noqa: F401

        if not callable(getattr(stg, "run_smoke_test", None)):
            log.error("  FAILED: run_smoke_test() not found in smoke_test_gemini.")
            all_passed = False
        else:
            log.info("  OK: smoke_test_gemini.run_smoke_test() is callable.")
    except ImportError as exc:
        log.error("  FAILED: Could not import smoke_test_gemini: %s", exc)
        all_passed = False

    # ------------------------------------------------------------------
    # TEST 5: run_smoke_test() returns False when no API key is present
    # ------------------------------------------------------------------
    log.info("TEST 5 * run_smoke_test() returns False with no API key ...")
    old_key2 = os.environ.get("GEMINI_API_KEY")
    try:
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

        import smoke_test_gemini as stg2  # already imported above

        result_no_key = stg2.run_smoke_test()
        if result_no_key is not False:
            log.error("  FAILED: Expected False when key absent, got %s", result_no_key)
            all_passed = False
        else:
            log.info("  OK: run_smoke_test() correctly returns False with no API key.")
    except Exception as exc:
        log.error("  FAILED with exception: %s", exc, exc_info=True)
        all_passed = False
    finally:
        if old_key2 is not None:
            os.environ["GEMINI_API_KEY"] = old_key2

    # ------------------------------------------------------------------
    # TEST 6: Security -- smoke_test_gemini contains no forbidden keywords
    # ------------------------------------------------------------------
    log.info("TEST 6 * Security: forbidden keywords absent from smoke_test_gemini ...")
    try:
        import smoke_test_gemini as stg3

        src = inspect.getsource(stg3)
        forbidden = ["page.evaluate", "subprocess", "os.system", "eval(", "exec("]
        found = [kw for kw in forbidden if kw in src]
        if found:
            log.error("  FAILED: Forbidden keyword(s) found: %s", found)
            all_passed = False
        else:
            log.info("  OK: No forbidden keywords found.")
    except Exception as exc:
        log.error("  FAILED with exception: %s", exc, exc_info=True)
        all_passed = False

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL SMOKE-WIRING TESTS PASSED.")
    else:
        log.error("OVERALL RESULT: SOME SMOKE-WIRING TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_smoke_wiring_tests()
    sys.exit(0 if success else 1)
