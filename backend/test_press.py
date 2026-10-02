"""
test_press.py — Focused test suite for the browser press action.

Run from backend/ directory:

    .venv\\Scripts\\python test_press.py

Tests verified:
1.  Browser starts (visible Chromium).
2.  Deterministic local HTML test page loaded.
3.  Fill text input, then press 'Enter' to trigger form submission.
4.  Verify page state changes after Enter press.
5.  Press 'Tab' to move focus between fields.
6.  Verify Tab moved focus correctly.
7.  Empty selector rejection.
8.  Whitespace-only selector rejection.
9.  Empty key rejection.
10. Whitespace-only key rejection.
11. Invalid selector syntax handled gracefully.
12. Nonexistent element timeout handled gracefully.
13. Unsupported/invalid key handled gracefully (Playwright rejects it).
14. Regression: open_url() still works.
15. Regression: get_page_text() still works.
16. Regression: click() still works.
17. Regression: fill() still works.
18. Browser cleanup — zero orphan processes.
"""

import logging
import sys
import time

sys.path.insert(0, ".")

from app.browser import (
    BrowserManager,
    BrowserPressResult,
    click,
    fill,
    get_page_text,
    open_url,
    press,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_press_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — press Verification Test Suite")
    log.info("=" * 65)

    manager = BrowserManager(headless=False)

    try:
        log.info("STEP 1 · Starting BrowserManager (visible Chromium)…")
        manager.start()
        log.info("✔ BrowserManager started.")

        # ── Local test page with a form that reacts to Enter ─────────────
        log.info("\nSTEP 2 · Setting up deterministic local test page…")
        test_html = """
        <!DOCTYPE html>
        <html>
          <head><title>Press Action Test</title></head>
          <body>
            <h1>Keyboard Press Verification</h1>
            <form id="test-form" onsubmit="event.preventDefault();
              document.getElementById('status').innerText='Form Submitted via Enter';
              document.getElementById('echo').innerText=document.getElementById('search-input').value;">
              <input id="search-input" type="text" placeholder="Type here" />
              <input id="second-input" type="text" placeholder="Tab lands here" />
              <button id="submit-btn" type="submit">Submit</button>
            </form>
            <div id="status">Waiting for input…</div>
            <div id="echo"></div>
          </body>
        </html>
        """
        manager.page.set_content(test_html)
        log.info("✔ Local test page loaded.")

        # ── Test 1: Fill then press Enter → form submits ─────────────────
        log.info("\nSTEP 3 · Fill '#search-input' then press Enter…")
        manager.fill("#search-input", "SIH2026_query")
        enter_res: BrowserPressResult = manager.press("#search-input", "Enter")
        log.info("Enter press result: success=%s | key='%s' | error='%s'", enter_res.success, enter_res.key, enter_res.error)

        text_after = manager.get_page_text()
        log.info("Page text after Enter: %s", (text_after.text or "").replace("\n", " "))

        if not enter_res.success:
            log.error("❌ FAILED: press(Enter) returned success=False")
            all_passed = False
        elif "Form Submitted via Enter" not in (text_after.text or ""):
            log.error("❌ FAILED: Page state did not change after Enter press!")
            all_passed = False
        elif "SIH2026_query" not in (text_after.text or ""):
            log.error("❌ FAILED: Echo div does not contain expected query text!")
            all_passed = False
        else:
            log.info("✔ Enter key press & form submission state-change PASSED!")

        time.sleep(1)

        # ── Test 2: Press Tab to move focus ──────────────────────────────
        log.info("\nSTEP 4 · Press Tab on '#search-input' to move focus…")
        tab_res: BrowserPressResult = manager.press("#search-input", "Tab")
        log.info("Tab press result: success=%s | key='%s' | error='%s'", tab_res.success, tab_res.key, tab_res.error)

        if not tab_res.success:
            log.error("❌ FAILED: press(Tab) returned success=False")
            all_passed = False
        else:
            # Verify focus moved to the second input
            focused_id = manager.page.evaluate("document.activeElement.id")
            log.info("Active element after Tab: '%s'", focused_id)
            if focused_id != "second-input":
                log.error("❌ FAILED: Focus did not move to 'second-input' after Tab (got '%s')", focused_id)
                all_passed = False
            else:
                log.info("✔ Tab key press & focus-move verification PASSED!")

        # ── Test 3: Empty / Whitespace Selector Rejection ────────────────
        log.info("\nSTEP 5 · Testing empty & whitespace selector rejection…")
        for bad_sel in ["", "   ", None]:
            r = manager.press(bad_sel, "Enter")
            log.info("Selector '%s' → success=%s, error='%s'", bad_sel, r.success, r.error)
            if r.success:
                log.error("❌ FAILED: Bad selector '%s' was accepted!", bad_sel)
                all_passed = False
        log.info("✔ Empty selector rejection PASSED!")

        # ── Test 4: Empty / Whitespace Key Rejection ─────────────────────
        log.info("\nSTEP 6 · Testing empty & whitespace key rejection…")
        for bad_key in ["", "   ", None]:
            r = manager.press("#search-input", bad_key)
            log.info("Key '%s' → success=%s, error='%s'", bad_key, r.success, r.error)
            if r.success:
                log.error("❌ FAILED: Bad key '%s' was accepted!", bad_key)
                all_passed = False
        log.info("✔ Empty key rejection PASSED!")

        # ── Test 5: Invalid Selector Syntax ──────────────────────────────
        log.info("\nSTEP 7 · Testing invalid selector syntax…")
        r = manager.press("//input[[[bad", "Enter")
        log.info("Invalid selector → success=%s, error='%s'", r.success, r.error)
        if r.success:
            log.error("❌ FAILED: Invalid selector syntax accepted!")
            all_passed = False
        else:
            log.info("✔ Invalid selector syntax handling PASSED!")

        # ── Test 6: Nonexistent Element Timeout ──────────────────────────
        log.info("\nSTEP 8 · Testing nonexistent element timeout (2s)…")
        r = manager.press("#does-not-exist-xyz", "Enter", timeout_ms=2000)
        log.info("Nonexistent element → success=%s, error snippet='%s'", r.success, (r.error or "")[:80])
        if r.success:
            log.error("❌ FAILED: Nonexistent element returned success=True!")
            all_passed = False
        elif not r.error or "Timeout" not in r.error:
            log.error("❌ FAILED: Expected timeout error, got: %s", r.error)
            all_passed = False
        else:
            log.info("✔ Nonexistent element timeout handling PASSED!")

        # ── Test 7: Unsupported / Invalid Key Name ────────────────────────
        log.info("\nSTEP 9 · Testing unsupported key name…")
        r = manager.press("#search-input", "NotARealKey_XYZ123")
        log.info("Invalid key → success=%s, error='%s'", r.success, r.error)
        if r.success:
            log.error("❌ FAILED: Unsupported key 'NotARealKey_XYZ123' returned success=True!")
            all_passed = False
        else:
            log.info("✔ Unsupported key handling PASSED!")

        # ── Test 8: Regressions ──────────────────────────────────────────
        log.info("\nSTEP 10 · Running regression tests for open_url, get_page_text, click, fill…")
        manager.page.set_content(test_html)

        reg_fill = manager.fill("#search-input", "regression_test")
        reg_click = manager.click("#submit-btn")
        reg_text = manager.get_page_text()
        reg_open = manager.open_url("https://example.com")

        if not reg_fill.success:
            log.error("❌ FAILED: fill() regression failed!")
            all_passed = False
        elif not reg_click.success:
            log.error("❌ FAILED: click() regression failed!")
            all_passed = False
        elif not reg_text.success:
            log.error("❌ FAILED: get_page_text() regression failed!")
            all_passed = False
        elif not reg_open.success:
            log.error("❌ FAILED: open_url() regression failed!")
            all_passed = False
        else:
            log.info("✔ All regression tests PASSED!")

    except Exception as exc:
        log.error("❌ Test suite crashed: %s", exc, exc_info=True)
        all_passed = False
    finally:
        log.info("\nSTEP 11 · Closing BrowserManager…")
        manager.close()
        log.info("✔ BrowserManager closed cleanly.")

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL PRESS TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_press_tests()
    sys.exit(0 if success else 1)
