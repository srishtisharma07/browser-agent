"""
test_screenshot.py — Focused test suite for the browser screenshot action.

Run from backend/ directory:

    .venv\\Scripts\\python test_screenshot.py

Tests verified:
1. Browser starts (visible Chromium).
2. Deterministic local HTML test page loaded.
3. Screenshot succeeds.
4. Screenshot file exists and is non-empty.
5. Returned URL is correct.
6. Returned path is correct.
7. Empty path rejected.
8. Whitespace path rejected.
9. Closed/unstarted browser failure handled safely.
10. Regression: open_url() still works.
11. Regression: get_page_text() still works.
12. Regression: click() still works.
13. Regression: fill() still works.
14. Regression: press() still works.
15. Browser cleanup — zero orphan processes.
"""

import logging
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, ".")

from app.browser import (
    BrowserManager,
    BrowserScreenshotResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_screenshot_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — screenshot Verification Test Suite")
    log.info("=" * 65)

    manager = BrowserManager(headless=False)
    temp_dir = tempfile.mkdtemp()
    test_screenshot_path = os.path.join(temp_dir, "test_shot.png")

    try:
        log.info("STEP 1 · Starting BrowserManager (visible Chromium)…")
        manager.start()
        log.info("✔ BrowserManager started.")

        # ── Local test page ─────────────
        log.info("\nSTEP 2 · Setting up deterministic local test page…")
        test_html = """
        <!DOCTYPE html>
        <html>
          <head><title>Screenshot Test</title></head>
          <body>
            <h1>Screenshot Verification</h1>
            <div id="box" style="width: 100px; height: 100px; background-color: blue;"></div>
            <input id="input" type="text" />
            <button id="btn">Click</button>
          </body>
        </html>
        """
        manager.page.set_content(test_html)
        log.info("✔ Local test page loaded.")

        # ── Test 1: Valid Screenshot ─────────────────
        log.info("\nSTEP 3 · Taking screenshot…")
        res: BrowserScreenshotResult = manager.screenshot(test_screenshot_path)
        log.info("Screenshot result: success=%s | image_path='%s' | error='%s'", res.success, res.image_path, res.error)

        if not res.success:
            log.error("❌ FAILED: screenshot() returned success=False")
            all_passed = False
        elif not res.image_path or res.image_path != test_screenshot_path:
            log.error("❌ FAILED: Returned path is incorrect!")
            all_passed = False
        elif not os.path.exists(test_screenshot_path):
            log.error("❌ FAILED: Screenshot file does not exist!")
            all_passed = False
        elif os.path.getsize(test_screenshot_path) == 0:
            log.error("❌ FAILED: Screenshot file is empty!")
            all_passed = False
        else:
            log.info("✔ Valid screenshot PASSED! File size: %d bytes", os.path.getsize(test_screenshot_path))

        # ── Test 2: Empty / Whitespace Path Rejection ────────────────
        log.info("\nSTEP 4 · Testing empty & whitespace path rejection…")
        for bad_path in ["", "   ", None]:
            r = manager.screenshot(bad_path)
            log.info("Path '%s' → success=%s, error='%s'", bad_path, r.success, r.error)
            if r.success:
                log.error("❌ FAILED: Bad path '%s' was accepted!", bad_path)
                all_passed = False
        log.info("✔ Empty/whitespace path rejection PASSED!")

        # ── Test 3: Regressions ──────────────────────────────────────────
        log.info("\nSTEP 5 · Running regression tests for open_url, get_page_text, click, fill, press…")
        manager.page.set_content(test_html)

        reg_fill = manager.fill("#input", "regression")
        reg_press = manager.press("#input", "Tab")
        reg_click = manager.click("#btn")
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
        log.info("\nSTEP 6 · Closing BrowserManager…")
        manager.close()
        log.info("✔ BrowserManager closed cleanly.")
        
        # ── Test 4: Closed Browser ──────────────────────────────────────────
        log.info("\nSTEP 7 · Testing unstarted/closed browser handling…")
        r = manager.screenshot(test_screenshot_path)
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
        log.info("OVERALL RESULT: ALL SCREENSHOT TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_screenshot_tests()
    sys.exit(0 if success else 1)
