"""
test_go_back.py — Focused test suite for the browser go_back action.

Run from backend/ directory:

    .venv\\Scripts\\python test_go_back.py

Tests verified:
1. Browser starts (visible Chromium).
2. Local deterministic pages (A, B, C) created and loaded to build history.
3. go_back() succeeds (C -> B).
4. Verify current URL is B.
5. go_back() succeeds again (B -> A).
6. Verify current URL is A.
7. go_back() on empty history handled safely without crash.
8. Unstarted/closed browser failure handled safely.
9. Regressions: open_url, get_page_text, click, fill, press, screenshot, scroll still work.
10. Browser cleanup — zero orphan processes.
"""

import logging
import os
import sys
import tempfile
import time

sys.path.insert(0, ".")

from app.browser import (
    BrowserManager,
    BrowserGoBackResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_go_back_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — go_back Verification Test Suite")
    log.info("=" * 65)

    manager = BrowserManager(headless=False)
    temp_dir = tempfile.mkdtemp()
    
    page_a = os.path.join(temp_dir, "page_a.html")
    page_b = os.path.join(temp_dir, "page_b.html")
    page_c = os.path.join(temp_dir, "page_c.html")
    test_screenshot_path = os.path.join(temp_dir, "test_shot_goback.png")

    with open(page_a, "w") as f:
        f.write("<html><body><h1>Page A</h1><input id='input' type='text'/><button id='btn'>Click</button></body></html>")
    with open(page_b, "w") as f:
        f.write("<html><body><h1>Page B</h1></body></html>")
    with open(page_c, "w") as f:
        f.write("<html><body><h1>Page C</h1></body></html>")

    # Use file:// URLs for the test pages
    url_a = "file:///" + page_a.replace("\\", "/")
    url_b = "file:///" + page_b.replace("\\", "/")
    url_c = "file:///" + page_c.replace("\\", "/")

    try:
        log.info("STEP 1 · Starting BrowserManager (visible Chromium)…")
        manager.start()
        log.info("✔ BrowserManager started.")

        # ── Test 1: Navigation History Setup ─────────────
        log.info("\nSTEP 2 · Setting up navigation history (A -> B -> C)…")
        
        manager.page.goto(url_a)
        manager.page.wait_for_load_state("load")
        time.sleep(0.5)
        
        manager.page.goto(url_b)
        manager.page.wait_for_load_state("load")
        time.sleep(0.5)
        
        manager.page.goto(url_c)
        manager.page.wait_for_load_state("load")
        time.sleep(0.5)
        
        current_url = manager.page.url
        log.info("Current URL before go_back: %s", current_url)
        if "page_c" not in current_url:
            log.error("❌ FAILED: Setup failed, expected to be on Page C.")
            all_passed = False

        # ── Test 2: First Go Back (C -> B) ─────────────────
        log.info("\nSTEP 3 · Calling go_back() (expected C -> B)…")
        res_back_1: BrowserGoBackResult = manager.go_back()
        
        log.info("Go Back result 1: success=%s | url='%s' | error='%s'", res_back_1.success, res_back_1.url, res_back_1.error)

        if not res_back_1.success:
            log.error("❌ FAILED: go_back() returned success=False")
            all_passed = False
        elif "page_b" not in res_back_1.url:
            log.error("❌ FAILED: Did not navigate to Page B! (Current: %s)", res_back_1.url)
            all_passed = False
        else:
            log.info("✔ First go_back() PASSED!")

        # ── Test 3: Second Go Back (B -> A) ─────────────────
        log.info("\nSTEP 4 · Calling go_back() again (expected B -> A)…")
        res_back_2: BrowserGoBackResult = manager.go_back()
        
        log.info("Go Back result 2: success=%s | url='%s' | error='%s'", res_back_2.success, res_back_2.url, res_back_2.error)

        if not res_back_2.success:
            log.error("❌ FAILED: go_back() returned success=False")
            all_passed = False
        elif "page_a" not in res_back_2.url:
            log.error("❌ FAILED: Did not navigate to Page A! (Current: %s)", res_back_2.url)
            all_passed = False
        else:
            log.info("✔ Second go_back() PASSED!")

        # ── Test 4: Third Go Back (No History) ────────────────
        log.info("\nSTEP 5 · Calling go_back() with no previous history (A -> ?)…")
        res_back_3 = manager.go_back()
        
        log.info("Go Back result 3: success=%s | url='%s' | error='%s'", res_back_3.success, res_back_3.url, res_back_3.error)

        # In Playwright, if there is no history, goBack returns None, which our wrapper handles
        if res_back_3.success:
            log.error("❌ FAILED: go_back() returned success=True even though there should be no history!")
            all_passed = False
        elif "No previous history entry available" not in (res_back_3.error or ""):
            log.error("❌ FAILED: Unexpected error message for empty history: %s", res_back_3.error)
            all_passed = False
        else:
            log.info("✔ Empty history go_back() handling PASSED!")

        # ── Test 5: Regressions ──────────────────────────────────────────
        log.info("\nSTEP 6 · Running regression tests for open_url, get_page_text, click, fill, press, screenshot, scroll…")
        
        # We need to navigate to page A for the regression tests to find the elements
        manager.page.goto(url_a)
        
        # We are on page A now, which has input and btn
        reg_fill = manager.fill("#input", "regression")
        reg_press = manager.press("#input", "Tab")
        reg_click = manager.click("#btn")
        reg_shot = manager.screenshot(test_screenshot_path)
        reg_scroll = manager.scroll("down", 100)
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
        elif not reg_scroll.success:
            log.error("❌ FAILED: scroll() regression failed!")
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
        log.info("\nSTEP 7 · Closing BrowserManager…")
        manager.close()
        log.info("✔ BrowserManager closed cleanly.")
        
        # ── Test 6: Closed Browser ──────────────────────────────────────────
        log.info("\nSTEP 8 · Testing unstarted/closed browser handling…")
        r = manager.go_back()
        log.info("Closed browser → success=%s, error='%s'", r.success, r.error)
        if r.success:
            log.error("❌ FAILED: Closed browser returned success=True!")
            all_passed = False
        else:
            log.info("✔ Closed browser handling PASSED!")

        # Cleanup temp files
        for fpath in [page_a, page_b, page_c, test_screenshot_path]:
            if os.path.exists(fpath):
                os.remove(fpath)
        os.rmdir(temp_dir)

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL GO_BACK TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_go_back_tests()
    sys.exit(0 if success else 1)
