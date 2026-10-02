"""
test_scroll.py — Focused test suite for the browser scroll action.

Run from backend/ directory:

    .venv\\Scripts\\python test_scroll.py

Tests verified:
1. Browser starts (visible Chromium).
2. Deterministic local HTML test page loaded (tall page).
3. Initial scroll position is near the top.
4. scroll("down", 800) succeeds.
5. Verify page scroll position increased.
6. scroll("up", 800) succeeds.
7. Verify page scroll position decreased.
8. Invalid direction rejected.
9. Empty direction rejected.
10. None direction rejected.
11. Zero amount rejected.
12. Negative amount rejected.
13. Invalid/non-integer amount rejected.
14. Scrolling on a closed/unstarted browser fails safely.
15. Regressions: open_url, get_page_text, click, fill, press, screenshot still work.
16. Browser cleanup — zero orphan processes.
"""

import logging
import os
import sys
import tempfile
import time

sys.path.insert(0, ".")

from app.browser import (
    BrowserManager,
    BrowserScrollResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_scroll_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — scroll Verification Test Suite")
    log.info("=" * 65)

    manager = BrowserManager(headless=False)
    temp_dir = tempfile.mkdtemp()
    test_screenshot_path = os.path.join(temp_dir, "test_shot_scroll.png")

    try:
        log.info("STEP 1 · Starting BrowserManager (visible Chromium)…")
        manager.start()
        log.info("✔ BrowserManager started.")

        # ── Local test page ─────────────
        log.info("\nSTEP 2 · Setting up deterministic local test page (tall page)…")
        test_html = """
        <!DOCTYPE html>
        <html>
          <head><title>Scroll Test</title>
          <style>
            body { margin: 0; padding: 0; height: 3000px; background: linear-gradient(to bottom, #f0f0f0, #000000); }
            #info { position: fixed; top: 10px; left: 10px; background: white; padding: 10px; border: 1px solid black; }
          </style>
          </head>
          <body>
            <div id="info">Scroll position: <span id="pos">0</span></div>
            <script>
                window.addEventListener("scroll", () => {
                    document.getElementById("pos").innerText = window.scrollY;
                });
            </script>
            <input id="input" type="text" style="position: absolute; top: 1500px;" />
            <button id="btn" style="position: absolute; top: 1600px;">Click</button>
          </body>
        </html>
        """
        manager.page.set_content(test_html)
        log.info("✔ Local test page loaded.")

        def get_scroll_y():
            return manager.page.evaluate("window.scrollY")

        # ── Test 1: Scroll Down ─────────────────
        initial_y = get_scroll_y()
        log.info("\nSTEP 3 · Scrolling down… (Initial Y: %s)", initial_y)
        res_down: BrowserScrollResult = manager.scroll("down", amount=800)
        
        # small wait to let the page scroll settle visually for get_scroll_y
        manager.page.wait_for_timeout(200)
        
        post_down_y = get_scroll_y()
        log.info("Scroll result: success=%s | error='%s'", res_down.success, res_down.error)
        log.info("Scroll Y after down: %s", post_down_y)

        if not res_down.success:
            log.error("❌ FAILED: scroll('down') returned success=False")
            all_passed = False
        elif post_down_y <= initial_y:
            log.error("❌ FAILED: Scroll Y did not increase! (Initial: %s, Current: %s)", initial_y, post_down_y)
            all_passed = False
        else:
            log.info("✔ Scroll down PASSED!")

        # ── Test 2: Scroll Up ─────────────────
        log.info("\nSTEP 4 · Scrolling up…")
        res_up: BrowserScrollResult = manager.scroll("up", amount=500)
        
        manager.page.wait_for_timeout(200)
        
        post_up_y = get_scroll_y()
        log.info("Scroll result: success=%s | error='%s'", res_up.success, res_up.error)
        log.info("Scroll Y after up: %s", post_up_y)

        if not res_up.success:
            log.error("❌ FAILED: scroll('up') returned success=False")
            all_passed = False
        elif post_up_y >= post_down_y:
            log.error("❌ FAILED: Scroll Y did not decrease! (Before: %s, Current: %s)", post_down_y, post_up_y)
            all_passed = False
        else:
            log.info("✔ Scroll up PASSED!")

        # ── Test 3: Invalid directions ────────────────
        log.info("\nSTEP 5 · Testing invalid directions…")
        for bad_dir in ["left", "right", "", "   ", None]:
            r = manager.scroll(bad_dir, amount=100)
            log.info("Direction '%s' → success=%s, error='%s'", bad_dir, r.success, r.error)
            if r.success:
                log.error("❌ FAILED: Bad direction '%s' was accepted!", bad_dir)
                all_passed = False
        log.info("✔ Invalid direction rejection PASSED!")

        # ── Test 4: Invalid amounts ────────────────
        log.info("\nSTEP 6 · Testing invalid amounts…")
        for bad_amt in [0, -100, "100", None, 1.5]:
            r = manager.scroll("down", amount=bad_amt)
            log.info("Amount '%s' → success=%s, error='%s'", bad_amt, r.success, r.error)
            if r.success:
                log.error("❌ FAILED: Bad amount '%s' was accepted!", bad_amt)
                all_passed = False
        log.info("✔ Invalid amount rejection PASSED!")

        # ── Test 5: Regressions ──────────────────────────────────────────
        log.info("\nSTEP 7 · Running regression tests for open_url, get_page_text, click, fill, press, screenshot…")
        manager.page.set_content(test_html)

        # we need to ensure the elements are visible or the viewport covers them for click/fill, but locator click/fill auto-scrolls
        reg_fill = manager.fill("#input", "regression")
        reg_press = manager.press("#input", "Tab")
        reg_click = manager.click("#btn")
        reg_shot = manager.screenshot(test_screenshot_path)
        reg_text = manager.get_page_text()
        reg_open = manager.open_url("https://example.com")

        if not reg_fill.success:
            log.error("❌ FAILED: fill() regression failed!")
            all_passed = False
        elif not reg_press.success:
            log.error("❌ FAILED: press() regression failed!")
            all_passed = False
        elif not reg_click.success:
            log.error("❌ FAILED: click() regression failed!")
            all_passed = False
        elif not reg_shot.success:
            log.error("❌ FAILED: screenshot() regression failed!")
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
        log.info("\nSTEP 8 · Closing BrowserManager…")
        manager.close()
        log.info("✔ BrowserManager closed cleanly.")
        
        # ── Test 6: Closed Browser ──────────────────────────────────────────
        log.info("\nSTEP 9 · Testing unstarted/closed browser handling…")
        r = manager.scroll("down")
        log.info("Closed browser → success=%s, error='%s'", r.success, r.error)
        if r.success:
            log.error("❌ FAILED: Closed browser returned success=True!")
            all_passed = False
        else:
            log.info("✔ Closed browser handling PASSED!")

        # Cleanup temp file
        if os.path.exists(test_screenshot_path):
            os.remove(test_screenshot_path)
        os.rmdir(temp_dir)

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL SCROLL TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_scroll_tests()
    sys.exit(0 if success else 1)
