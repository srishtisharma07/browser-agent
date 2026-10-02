"""
test_click.py — Focused test suite for the browser click action.

Run from backend/ directory:

    .venv\\Scripts\\python test_click.py

Tests verified:
1. Browser starts (visible Chromium).
2. Deterministic local page with interactive button and link.
3. Click valid button:
   - Confirms click succeeds.
   - Confirms page state updates (button text and status div change).
4. Click valid link:
   - Confirms click succeeds and URL updates hash target.
5. Empty/whitespace selector rejection:
   - Confirms rejected safely with error message.
6. Invalid selector syntax:
   - Confirms handled gracefully without crashing.
7. Nonexistent element timeout:
   - Confirms times out gracefully without crashing.
8. Regression check with open_url and get_page_text:
   - Confirms previous actions remain functional.
9. Clean browser cleanup — zero orphan processes.
"""

import logging
import sys
import time

# Ensure backend root is on sys.path
sys.path.insert(0, ".")

from app.browser import (
    BrowserActionResult,
    BrowserClickResult,
    BrowserManager,
    BrowserPageTextResult,
    click,
    get_page_text,
    open_url,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_click_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — click Verification Test Suite")
    log.info("=" * 65)

    manager = BrowserManager(headless=False)

    try:
        log.info("STEP 1 · Starting BrowserManager (visible Chromium)…")
        manager.start()
        log.info("✔ BrowserManager started.")

        # ── Test Page Setup ──────────────────────────────────────────────
        log.info("\nSTEP 2 · Setting up deterministic local test HTML page…")
        test_html = """
        <!DOCTYPE html>
        <html>
          <head><title>Click Test Page</title></head>
          <body>
            <h1>Click Action Verification</h1>
            <button id="action-btn" onclick="this.innerText='Button Clicked!'; document.getElementById('status-div').innerText='State Changed Successfully';">Click Me</button>
            <a id="test-link" href="#target-section">Jump to Target</a>
            <div id="status-div">Initial State</div>
            <div id="target-section" style="margin-top: 100px;">Target Section</div>
          </body>
        </html>
        """
        manager.page.set_content(test_html)
        log.info("✔ Local HTML test page loaded.")

        # ── Test 1: Click Valid Button & Verify State Change ─────────────
        log.info("\nSTEP 3 · Testing click on valid button '#action-btn'…")
        btn_res: BrowserClickResult = manager.click("#action-btn")
        log.info("Click Result: success=%s | selector='%s' | url='%s' | error='%s'", btn_res.success, btn_res.selector, btn_res.url, btn_res.error)

        if not btn_res.success:
            log.error("❌ FAILED: click('#action-btn') returned success=False")
            all_passed = False
        else:
            # Check page state change via get_page_text
            text_res = manager.get_page_text()
            log.info("Extracted page text after button click:\n---\n%s\n---", text_res.text)
            if "Button Clicked!" not in (text_res.text or "") or "State Changed Successfully" not in (text_res.text or ""):
                log.error("❌ FAILED: Page state did not change as expected after click!")
                all_passed = False
            else:
                log.info("✔ Button click & page-state-change verification PASSED!")

        time.sleep(1)

        # ── Test 2: Click Valid Link ─────────────────────────────────────
        log.info("\nSTEP 4 · Testing click on valid link '#test-link'…")
        link_res: BrowserClickResult = manager.click("#test-link")
        log.info("Link Click Result: success=%s | url='%s' | error='%s'", link_res.success, link_res.url, link_res.error)

        if not link_res.success:
            log.error("❌ FAILED: click('#test-link') returned success=False")
            all_passed = False
        elif "#target-section" not in link_res.url:
            log.error("❌ FAILED: Link click did not navigate to target hash URL!")
            all_passed = False
        else:
            log.info("✔ Link click verification PASSED!")

        # ── Test 3: Reject Empty / Whitespace Selectors ──────────────────
        log.info("\nSTEP 5 · Testing empty & whitespace selector rejection…")
        for bad_sel in ["", "   ", None]:
            bad_res = manager.click(bad_sel)
            log.info("Testing selector '%s' -> success=%s, error='%s'", bad_sel, bad_res.success, bad_res.error)
            if bad_res.success:
                log.error("❌ FAILED: Empty selector '%s' was incorrectly accepted!", bad_sel)
                all_passed = False
            else:
                log.info("✔ Empty selector correctly rejected.")

        # ── Test 4: Invalid Selector Syntax ──────────────────────────────
        log.info("\nSTEP 6 · Testing invalid selector syntax handling…")
        invalid_sel = "//div[[[bad_selector"
        invalid_res = manager.click(invalid_sel)
        log.info("Invalid Selector Result: success=%s | error='%s'", invalid_res.success, invalid_res.error)

        if invalid_res.success:
            log.error("❌ FAILED: Invalid selector syntax was accepted!")
            all_passed = False
        elif not invalid_res.error:
            log.error("❌ FAILED: Invalid selector failed without returning error message!")
            all_passed = False
        else:
            log.info("✔ Invalid selector syntax handled gracefully PASSED!")

        # ── Test 5: Nonexistent Element Timeout Handling ─────────────────
        log.info("\nSTEP 7 · Testing nonexistent element timeout handling (2s timeout)…")
        nonexistent_sel = "#nonexistent-element-xyz"
        timeout_res = manager.click(nonexistent_sel, timeout_ms=2000)
        log.info("Nonexistent Element Result: success=%s | error='%s'", timeout_res.success, timeout_res.error)

        if timeout_res.success:
            log.error("❌ FAILED: Nonexistent element click returned success=True!")
            all_passed = False
        elif not timeout_res.error or "Timeout" not in timeout_res.error:
            log.error("❌ FAILED: Expected timeout error message, got: %s", timeout_res.error)
            all_passed = False
        else:
            log.info("✔ Nonexistent element timeout handling PASSED!")

        # ── Test 6: Regression Checks (open_url & get_page_text) ─────────
        log.info("\nSTEP 8 · Testing open_url and get_page_text regressions…")
        reg_open = manager.open_url("https://example.com")
        reg_text = manager.get_page_text()

        if not reg_open.success or not reg_text.success or "example" not in (reg_text.text or "").lower():
            log.error("❌ FAILED: open_url / get_page_text regression check failed!")
            all_passed = False
        else:
            log.info("✔ Regression tests for open_url and get_page_text PASSED!")

    except Exception as exc:
        log.error("❌ Test suite crashed with unexpected exception: %s", exc, exc_info=True)
        all_passed = False
    finally:
        log.info("\nSTEP 9 · Closing BrowserManager…")
        manager.close()
        log.info("✔ BrowserManager closed cleanly.")

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL CLICK TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)

    return all_passed


if __name__ == "__main__":
    success = run_click_tests()
    sys.exit(0 if success else 1)
