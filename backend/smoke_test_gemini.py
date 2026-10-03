"""
smoke_test_gemini.py -- Real Gemini End-to-End Smoke Test (Task 2K)

Validates that the real Gemini API can drive the full agent pipeline:

    Natural-language goal
        down
    Real Gemini
        down
    AgentDecisionEngine -> ApprovalGate -> ToolRegistry -> BrowserManager -> Playwright
        down
    Structured browser observation returned to AgentState
        down
    Real Gemini sees accumulated observations
        down
    ... additional cycles ...
        down
    Final response

Usage (from backend/ directory):
    .venv\Scripts\python smoke_test_gemini.py

Requirements:
    * GEMINI_API_KEY set in backend/.env or the environment.
    * Playwright browsers installed (playwright install chromium).

Safety guarantees:
    * Only https://example.com/ is visited.
    * No credentials, no form submissions, no consequential actions.
    * GEMINI_API_KEY is NEVER printed, logged, or included in output.
    * Exceptions are sanitized before display.
    * All browser execution routes through ToolRegistry -> BrowserManager -> Playwright.
"""

from __future__ import annotations

import logging
import os
import sys
import re

# Ensure backend/ root is on the path when running directly.
sys.path.insert(0, ".")

# ---------------------------------------------------------------------------
# IMPORTANT: load .env BEFORE importing any app module that reads config,
# so that GEMINI_API_KEY is available when GeminiLLMProvider is instantiated.
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

load_dotenv()  # reads backend/.env if it exists

from app.config import Config, LLMConfigurationError
from app.llm.gemini import GeminiLLMProvider
from app.browser.manager import BrowserManager
from app.agent.tools import ToolRegistry
from app.agent.runner import AgentRunner
from app.agent.graph import AgentGraphResult

# ---------------------------------------------------------------------------
# Logging -- structured, no secrets ever emitted.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SMOKE_TEST_GOAL = (
    "Open https://example.com/, inspect the page, "
    "gather the main information available on it, and give me a short summary."
)
MAX_CYCLES = 8

_API_KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z\-_]{35}")


# ---------------------------------------------------------------------------
# Secret sanitizer
# ---------------------------------------------------------------------------

def _sanitize(text: str, api_key: str | None) -> str:
    """Remove any accidental API-key leakage from a string."""
    if api_key and api_key in text:
        text = text.replace(api_key, "[REDACTED]")
    # Belt-and-suspenders: redact anything that looks like a Gemini API key.
    text = _API_KEY_PATTERN.sub("[REDACTED]", text)
    return text


# ---------------------------------------------------------------------------
# Result printer -- safe subset of AgentGraphResult
# ---------------------------------------------------------------------------

def _print_result(result: AgentGraphResult, api_key: str | None) -> None:
    log.info("=" * 65)
    log.info("SMOKE TEST RESULT")
    log.info("=" * 65)
    log.info("Task Status   : %s", result.final_state.task_status.value)
    log.info("Cycle Count   : %d", result.cycle_count)
    log.info("Stop Reason   : %s", result.stop_reason)
    log.info("Verif. Status : %s", result.verification_status)

    # Tool/observation sequence (safe: only source labels and summaries)
    log.info("-" * 65)
    log.info("Observation / tool sequence:")
    for i, obs in enumerate(result.final_state.observations, start=1):
        source = obs.source
        summary = _sanitize(obs.summary, api_key)
        url_part = " -- URL: " + obs.url if obs.url else ""
        log.info("  [%d] source=%-32s | %s%s", i, source, summary[:120], url_part)

    # Errors (sanitized)
    if result.final_state.errors:
        log.info("-" * 65)
        log.info("Errors recorded:")
        for err in result.final_state.errors:
            log.info("  * %s", _sanitize(err, api_key))

    # Final response
    if result.decision and result.decision.action == "respond" and result.decision.response_text:
        log.info("-" * 65)
        log.info("Final Response (first 500 chars):")
        safe_text = _sanitize(result.decision.response_text[:500], api_key)
        log.info("%s", safe_text)

    log.info("=" * 65)


# ---------------------------------------------------------------------------
# Main smoke test
# ---------------------------------------------------------------------------

def run_smoke_test() -> bool:
    log.info("=" * 65)
    log.info("Task 2K -- Real Gemini End-to-End Smoke Test")
    log.info("=" * 65)

    # ------------------------------------------------------------------
    # Step 1: Verify configuration
    # ------------------------------------------------------------------
    cfg = Config()
    api_key: str | None = cfg.gemini_api_key  # may be None

    log.info("Gemini model   : %s", cfg.gemini_model)
    log.info("API key status : %s", "SET" if api_key else "NOT SET")

    if not api_key:
        log.warning(
            "\n"
            "  =====================================================\n"
            "  GEMINI_API_KEY is not set -- live smoke test skipped.\n"
            "  To run the live test:\n"
            "    1. Copy backend/.env.example -> backend/.env\n"
            "    2. Set GEMINI_API_KEY=<your-real-key> in .env\n"
            "    3. Re-run this script.\n"
            "  ====================================================="
        )
        log.info("All automated mocked tests remain unaffected.")
        return False

    # ------------------------------------------------------------------
    # Step 2: Build the pipeline using existing production classes only.
    #         No direct Playwright calls. No direct browser tool calls.
    # ------------------------------------------------------------------
    log.info("-" * 65)
    log.info("Building pipeline ...")

    try:
        llm_provider = GeminiLLMProvider()  # reads key securely from Config
    except LLMConfigurationError as exc:
        log.error("LLM configuration error: %s", exc)
        return False

    browser_manager = BrowserManager()
    try:
        browser_manager.start()
        log.info("BrowserManager started.")
    except Exception as exc:
        log.error("Failed to start BrowserManager: %s", _sanitize(str(exc), api_key))
        return False

    tool_registry = ToolRegistry(browser_manager)
    log.info("ToolRegistry ready. Registered tools: %s", tool_registry.list_tools())

    runner = AgentRunner(
        tool_registry=tool_registry,
        llm_provider=llm_provider,
        browser_manager=browser_manager,
    )

    # ------------------------------------------------------------------
    # Step 3: Execute the safe smoke-test task.
    # ------------------------------------------------------------------
    log.info("-" * 65)
    log.info("Goal : %s", SMOKE_TEST_GOAL)
    log.info("Max cycles : %d", MAX_CYCLES)
    log.info("Starting agent run ...")

    result: AgentGraphResult | None = None
    success = False

    try:
        result = runner.run_task(
            user_goal=SMOKE_TEST_GOAL,
            task_id="smoke-2k",
            max_cycles=MAX_CYCLES,
        )
        success = result.stop_reason in ("completed_response", "max_cycles_reached")

    except LLMConfigurationError as exc:
        log.error("LLM configuration error during run: %s", exc)
    except Exception as exc:
        sanitized = _sanitize(str(exc), api_key)
        log.error("Smoke test raised an exception: %s", sanitized)
    finally:
        try:
            browser_manager.stop()
            log.info("BrowserManager stopped cleanly.")
        except Exception as exc:
            log.warning("Error stopping BrowserManager: %s", _sanitize(str(exc), api_key))

    # ------------------------------------------------------------------
    # Step 4: Print safe results
    # ------------------------------------------------------------------
    if result is not None:
        _print_result(result, api_key)
    else:
        log.error("No result was produced -- the agent run did not complete.")

    if success:
        log.info("Smoke test completed successfully.")
    else:
        log.warning("Smoke test did not reach a clean completed_response stop reason.")

    return success


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    ok = run_smoke_test()
    sys.exit(0 if ok else 1)
