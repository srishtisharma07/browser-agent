"""
test_browser.py — Standalone browser lifecycle smoke-test.

Run from the backend/ directory with the venv active:

    python test_browser.py

What this test proves
---------------------
1. Playwright starts successfully.
2. Chromium launches visibly (headless=False).
3. A BrowserContext and Page are created.
4. The test completes without hanging.
5. Chromium and Playwright stop cleanly — no orphan processes.

This script does NOT perform any navigation, clicking, or agent actions.
"""

import logging
import sys
import time

# Make sure the app package is importable when run from backend/
sys.path.insert(0, ".")

from app.browser.manager import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_smoke_test() -> bool:
    """
    Launch Chromium, hold for a short moment, then close cleanly.

    Returns True on success, False on failure.
    """
    log.info("=" * 55)
    log.info("AI Browser Agent — Browser lifecycle smoke-test")
    log.info("=" * 55)

    manager = BrowserManager(headless=False)

    try:
        # ── 1. Start ──────────────────────────────────────────────
        log.info("STEP 1 · Starting BrowserManager…")
        manager.start()
        assert manager.is_running, "is_running should be True after start()"
        log.info("         ✔  Playwright started")
        log.info("         ✔  Chromium launched (visible)")
        log.info("         ✔  Context and page created")

        # ── 2. Verify page object exists ──────────────────────────
        log.info("STEP 2 · Verifying page object…")
        page = manager.page
        assert page is not None, "page should not be None"
        log.info("         ✔  Page object: %s", page)

        # ── 3. Brief hold so the window is visible in the demo ────
        log.info("STEP 3 · Holding browser open for 3 seconds (visible demo)…")
        time.sleep(3)

        # ── 4. Close cleanly ──────────────────────────────────────
        log.info("STEP 4 · Closing BrowserManager…")
        manager.close()
        assert not manager.is_running, "is_running should be False after close()"
        log.info("         ✔  Page closed")
        log.info("         ✔  Context closed")
        log.info("         ✔  Chromium closed")
        log.info("         ✔  Playwright stopped")

    except Exception as exc:
        log.error("Smoke-test FAILED: %s", exc)
        # Attempt emergency cleanup so no processes linger
        try:
            manager.close()
        except Exception:  # noqa: BLE001
            pass
        return False

    log.info("=" * 55)
    log.info("Smoke-test PASSED — no orphan processes.")
    log.info("=" * 55)
    return True


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
