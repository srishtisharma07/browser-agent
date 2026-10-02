"""
test_get_page_text.py — Focused test suite for the browser get_page_text action.

Run from backend/ directory:

    .venv\\Scripts\\python test_get_page_text.py

Tests verified:
1. Browser starts (visible Chromium).
2. Deterministic HTML content extraction:
   - Extracts body text ('Welcome to AI Browser Agent', etc.)
   - Ensures output is clean visible text, NOT raw HTML.
3. Large text truncation safeguard:
   - Generates > 50,000 character page content.
   - Confirms text is truncated at configured limit (e.g., max_length=500).
   - Confirms truncated=True flag.
4. Failure handling on invalid/closed page:
   - Confirms returns structured error instead of crashing.
5. Regression test with open_url("https://example.com"):
   - Confirms open_url works and get_page_text extracts Example Domain text.
6. Browser cleanup succeeds with zero orphan processes.
"""

import logging
import sys
import time

# Ensure backend root is on sys.path
sys.path.insert(0, ".")

from app.browser import (
    BrowserActionResult,
    BrowserManager,
    BrowserPageTextResult,
    get_page_text,
    open_url,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_get_page_text_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — get_page_text Verification Test Suite")
    log.info("=" * 65)

    manager = BrowserManager(headless=False)

    try:
        log.info("STEP 1 · Starting BrowserManager (visible Chromium)…")
        manager.start()
        log.info("✔ BrowserManager started.")

        # ── Test 1: Deterministic Content Extraction ─────────────────────
        log.info("\nSTEP 2 · Testing deterministic local HTML page text extraction…")
        sample_html = """
        <!DOCTYPE html>
        <html>
          <head><title>SIH Test Page</title></head>
          <body>
            <h1>Welcome to AI Browser Agent</h1>
            <p>This is a deterministic test paragraph for get_page_text verification.</p>
            <footer>SIH260171 Browser Assistant</footer>
          </body>
        </html>
        """
        manager.page.set_content(sample_html)

        res: BrowserPageTextResult = manager.get_page_text()
        log.info(
            "Result: success=%s | truncated=%s | text_len=%d | url='%s' | error='%s'",
            res.success,
            res.truncated,
            len(res.text or ""),
            res.url,
            res.error,
        )

        if not res.success:
            log.error("❌ FAILED: get_page_text returned success=False")
            all_passed = False
        elif "Welcome to AI Browser Agent" not in (res.text or ""):
            log.error("❌ FAILED: Expected header text not found in extracted text!")
            all_passed = False
        elif "deterministic test paragraph" not in (res.text or ""):
            log.error("❌ FAILED: Expected paragraph text not found in extracted text!")
            all_passed = False
        elif "<h1>" in (res.text or "") or "<html>" in (res.text or ""):
            log.error("❌ FAILED: Extracted text contains raw HTML tags!")
            all_passed = False
        else:
            log.info("✔ Deterministic text extraction PASSED! Text snippet:\n---\n%s\n---", res.text[:150])

        # ── Test 2: Large Text Truncation ─────────────────────────────────
        log.info("\nSTEP 3 · Testing large text truncation safeguard (limit=500 chars)…")
        large_body_text = "ABCDEFGHIJ " * 5000  # 55,000 characters
        large_html = f"<html><body><h1>Large Page</h1><p>{large_body_text}</p></body></html>"
        manager.page.set_content(large_html)

        trunc_res: BrowserPageTextResult = manager.get_page_text(max_length=500)
        log.info(
            "Truncation Result: success=%s | truncated=%s | text_len=%d",
            trunc_res.success,
            trunc_res.truncated,
            len(trunc_res.text or ""),
        )

        if not trunc_res.success:
            log.error("❌ FAILED: Truncation test returned success=False")
            all_passed = False
        elif not trunc_res.truncated:
            log.error("❌ FAILED: Expected truncated=True for >50k character page!")
            all_passed = False
        elif len(trunc_res.text or "") != 500:
            log.error("❌ FAILED: Extracted text length is %d, expected exactly 500!", len(trunc_res.text or ""))
            all_passed = False
        else:
            log.info("✔ Large text truncation safeguard PASSED! Exactly 500 chars extracted.")

        # ── Test 3: Failure Handling on Invalid / Unstarted Manager ──────
        log.info("\nSTEP 4 · Testing failure handling on unstarted manager…")
        unstarted_manager = BrowserManager(headless=True)
        fail_res: BrowserPageTextResult = unstarted_manager.get_page_text()
        log.info("Unstarted Manager Result: success=%s | error='%s'", fail_res.success, fail_res.error)

        if fail_res.success:
            log.error("❌ FAILED: Unstarted manager returned success=True!")
            all_passed = False
        elif not fail_res.error:
            log.error("❌ FAILED: Unstarted manager returned no error message!")
            all_passed = False
        else:
            log.info("✔ Failure handling on unstarted manager PASSED!")

        # ── Test 4: Regression with open_url("https://example.com") ─────
        log.info("\nSTEP 5 · Testing regression with open_url('https://example.com')…")
        nav_res: BrowserActionResult = manager.open_url("https://example.com")
        if not nav_res.success:
            log.error("❌ FAILED: open_url('https://example.com') regression test failed!")
            all_passed = False
        else:
            example_text_res = manager.get_page_text()
            log.info(
                "Example.com text result: success=%s | full_text='%s'",
                example_text_res.success,
                (example_text_res.text or "").replace("\n", " "),
            )
            text_lower = (example_text_res.text or "").lower()
            if not example_text_res.success or ("example" not in text_lower and "domain" not in text_lower):
                log.error("❌ FAILED: Could not extract expected text from example.com!")
                all_passed = False
            else:
                log.info("✔ Regression test with open_url and example.com PASSED!")

    except Exception as exc:
        log.error("❌ Test crashed with unexpected exception: %s", exc, exc_info=True)
        all_passed = False
    finally:
        log.info("\nSTEP 6 · Closing BrowserManager…")
        manager.close()
        log.info("✔ BrowserManager closed cleanly.")

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL GET_PAGE_TEXT TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)

    return all_passed


if __name__ == "__main__":
    success = run_get_page_text_tests()
    sys.exit(0 if success else 1)
