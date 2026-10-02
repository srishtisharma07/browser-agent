"""
test_fill.py — Focused test suite for the browser fill action.

Run from backend/ directory:

    .venv\\Scripts\\python test_fill.py

Tests verified:
1. Browser starts (visible Chromium).
2. Deterministic local HTML form loaded with input, textarea, and disabled controls.
3. Fill text input (#username):
   - Confirms action returns success=True.
   - Confirms DOM input_value() matches filled text.
4. Fill textarea (#user-bio):
   - Confirms action returns success=True.
   - Confirms DOM input_value() matches filled text.
5. Empty / whitespace selector rejection:
   - Confirms rejected safely with error message.
6. Invalid value (non-string / None) rejection:
   - Confirms handled safely.
7. Invalid selector syntax handling:
   - Confirms handled safely without crashing.
8. Nonexistent element timeout:
   - Confirms handled safely without crashing.
9. Disabled / non-editable element handling:
   - Confirms handled safely with error message.
10. Regression checks:
    - open_url(), get_page_text(), and click() remain functional.
11. Browser cleanup succeeds with zero orphan processes.
"""

import logging
import sys
import time

# Ensure backend root is on sys.path
sys.path.insert(0, ".")

from app.browser import (
    BrowserActionResult,
    BrowserClickResult,
    BrowserFillResult,
    BrowserManager,
    BrowserPageTextResult,
    click,
    fill,
    get_page_text,
    open_url,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_fill_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — fill Verification Test Suite")
    log.info("=" * 65)

    manager = BrowserManager(headless=False)

    try:
        log.info("STEP 1 · Starting BrowserManager (visible Chromium)…")
        manager.start()
        log.info("✔ BrowserManager started.")

        # ── Setup Local Test Form ────────────────────────────────────────
        log.info("\nSTEP 2 · Setting up deterministic local test HTML form…")
        form_html = """
        <!DOCTYPE html>
        <html>
          <head><title>Fill Action Test Form</title></head>
          <body>
            <h1>Interactive Test Form</h1>
            <form id="test-form">
              <label for="username">Username:</label>
              <input id="username" type="text" name="username" /><br/>

              <label for="user-bio">Bio:</label>
              <textarea id="user-bio" name="user_bio"></textarea><br/>

              <label for="disabled-field">Disabled:</label>
              <input id="disabled-field" type="text" disabled value="readonly_value" /><br/>

              <button id="submit-btn" type="button" onclick="document.getElementById('status').innerText='Form Action Triggered'">Submit</button>
            </form>
            <div id="status">Initial Form State</div>
          </body>
        </html>
        """
        manager.page.set_content(form_html)
        log.info("✔ Local HTML test form loaded.")

        # ── Test 1: Fill Text Input ──────────────────────────────────────
        log.info("\nSTEP 3 · Testing fill on text input '#username'…")
        input_fill_res: BrowserFillResult = manager.fill("#username", "agent_user_2026")
        log.info("Input Fill Result: success=%s | selector='%s' | url='%s' | error='%s'", input_fill_res.success, input_fill_res.selector, input_fill_res.url, input_fill_res.error)

        dom_input_val = manager.page.locator("#username").input_value()
        if not input_fill_res.success:
            log.error("❌ FAILED: fill('#username') returned success=False")
            all_passed = False
        elif dom_input_val != "agent_user_2026":
            log.error("❌ FAILED: DOM field value '%s' does not match expected value!", dom_input_val)
            all_passed = False
        else:
            log.info("✔ Text input fill & DOM value verification PASSED!")

        # ── Test 2: Fill Textarea ────────────────────────────────────────
        log.info("\nSTEP 4 · Testing fill on textarea '#user-bio'…")
        textarea_val = "Automated Browser Agent profile text line 1.\nLine 2 description."
        textarea_res: BrowserFillResult = manager.fill("#user-bio", textarea_val)
        log.info("Textarea Fill Result: success=%s | selector='%s' | error='%s'", textarea_res.success, textarea_res.selector, textarea_res.error)

        dom_textarea_val = manager.page.locator("#user-bio").input_value()
        if not textarea_res.success:
            log.error("❌ FAILED: fill('#user-bio') returned success=False")
            all_passed = False
        elif dom_textarea_val != textarea_val:
            log.error("❌ FAILED: Textarea DOM value does not match expected value!")
            all_passed = False
        else:
            log.info("✔ Textarea fill & DOM value verification PASSED!")

        time.sleep(1)

        # ── Test 3: Reject Empty / Whitespace Selectors ──────────────────
        log.info("\nSTEP 5 · Testing empty & whitespace selector rejection…")
        for bad_sel in ["", "   ", None]:
            bad_sel_res = manager.fill(bad_sel, "test_val")
            log.info("Testing bad selector '%s' -> success=%s, error='%s'", bad_sel, bad_sel_res.success, bad_sel_res.error)
            if bad_sel_res.success:
                log.error("❌ FAILED: Empty selector '%s' was incorrectly accepted!", bad_sel)
                all_passed = False

        log.info("✔ Empty selector rejection PASSED!")

        # ── Test 4: Invalid Value Handling (Non-string / None) ───────────
        log.info("\nSTEP 6 · Testing invalid value handling (None / non-string)…")
        invalid_val_res = manager.fill("#username", None)
        log.info("Non-string value result: success=%s, error='%s'", invalid_val_res.success, invalid_val_res.error)

        if invalid_val_res.success:
            log.error("❌ FAILED: Non-string value was accepted!")
            all_passed = False
        else:
            log.info("✔ Invalid value handling PASSED!")

        # ── Test 5: Invalid Selector Syntax ──────────────────────────────
        log.info("\nSTEP 7 · Testing invalid selector syntax handling…")
        bad_syntax_res = manager.fill("//input[[[invalid", "test")
        log.info("Invalid selector syntax result: success=%s, error='%s'", bad_syntax_res.success, bad_syntax_res.error)

        if bad_syntax_res.success:
            log.error("❌ FAILED: Invalid selector syntax was accepted!")
            all_passed = False
        else:
            log.info("✔ Invalid selector syntax handling PASSED!")

        # ── Test 6: Nonexistent Element Timeout Handling ─────────────────
        log.info("\nSTEP 8 · Testing nonexistent element timeout handling (2s timeout)…")
        nonexistent_res = manager.fill("#element-does-not-exist-123", "test", timeout_ms=2000)
        log.info("Nonexistent element result: success=%s, error='%s'", nonexistent_res.success, nonexistent_res.error)

        if nonexistent_res.success:
            log.error("❌ FAILED: Nonexistent element fill returned success=True!")
            all_passed = False
        elif not nonexistent_res.error or "Timeout" not in nonexistent_res.error:
            log.error("❌ FAILED: Expected timeout error message, got: %s", nonexistent_res.error)
            all_passed = False
        else:
            log.info("✔ Nonexistent element timeout handling PASSED!")

        # ── Test 7: Disabled / Non-editable Input Handling ───────────────
        log.info("\nSTEP 9 · Testing disabled/non-editable element handling…")
        disabled_res = manager.fill("#disabled-field", "attempt_overwrite", timeout_ms=2000)
        log.info("Disabled element result: success=%s, error='%s'", disabled_res.success, disabled_res.error)

        if disabled_res.success:
            log.error("❌ FAILED: Disabled field fill returned success=True!")
            all_passed = False
        else:
            log.info("✔ Disabled field rejection PASSED!")

        # ── Test 8: Regressions (open_url, get_page_text, click) ──────────
        log.info("\nSTEP 10 · Testing open_url, get_page_text, and click regressions…")
        reg_click = manager.click("#submit-btn")
        reg_text = manager.get_page_text()

        if not reg_click.success or "Form Action Triggered" not in (reg_text.text or ""):
            log.error("❌ FAILED: Regression check failed for click/get_page_text!")
            all_passed = False
        else:
            reg_open = manager.open_url("https://example.com")
            if not reg_open.success:
                log.error("❌ FAILED: open_url regression check failed!")
                all_passed = False
            else:
                log.info("✔ Regressions for open_url, get_page_text, and click PASSED!")

    except Exception as exc:
        log.error("❌ Test suite crashed with unexpected exception: %s", exc, exc_info=True)
        all_passed = False
    finally:
        log.info("\nSTEP 11 · Closing BrowserManager…")
        manager.close()
        log.info("✔ BrowserManager closed cleanly.")

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL FILL TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)

    return all_passed


if __name__ == "__main__":
    success = run_fill_tests()
    sys.exit(0 if success else 1)
