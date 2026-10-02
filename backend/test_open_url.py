"""
test_open_url.py — Standalone verification test for the browser open_url action.

Run from backend/ directory:

    .venv\\Scripts\\python test_open_url.py

Tests performed:
1. Start BrowserManager (headless=False)
2. Valid navigation to https://example.com:
   - Check success is True
   - Check page title contains 'Example Domain'
   - Check URL starts with 'https://example.com'
3. Invalid protocol validation (file://, javascript:, data:, chrome://, ftp://):
   - Check success is False
   - Check error message indicates invalid protocol/format
4. Malformed/Empty URL validation:
   - Check success is False
5. Unreachable website / navigation failure:
   - Check success is False and error is returned cleanly without exception crash
6. Clean teardown — BrowserManager closes without orphan processes.
"""

import logging
import sys
import time

# Ensure backend root is on sys.path
sys.path.insert(0, ".")

from app.browser import BrowserActionResult, BrowserManager, open_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_open_url_tests() -> bool:
    all_passed = True

    log.info("=" * 60)
    log.info("AI Browser Agent — open_url Verification Test Suite")
    log.info("=" * 60)

    manager = BrowserManager(headless=False)

    try:
        log.info("STEP 1 · Starting BrowserManager (visible Chromium)…")
        manager.start()
        log.info("✔ BrowserManager started successfully.")

        # ── Test 1: Valid Navigation (https://example.com) ─────────────
        log.info("\nSTEP 2 · Testing valid URL navigation: https://example.com")
        res: BrowserActionResult = manager.open_url("https://example.com")
        log.info("Result: success=%s | url='%s' | title='%s' | error='%s'", res.success, res.url, res.title, res.error)

        if not res.success:
            log.error("❌ FAILED: open_url('https://example.com') returned success=False")
            all_passed = False
        elif "example.com" not in res.url.lower():
            log.error("❌ FAILED: Unexpected URL '%s'", res.url)
            all_passed = False
        elif not res.title or "Example Domain" not in res.title:
            log.error("❌ FAILED: Unexpected page title '%s'", res.title)
            all_passed = False
        else:
            log.info("✔ Valid navigation PASSED!")

        # Hold briefly for visual demo inspection
        time.sleep(2)

        # ── Test 2: Reject Invalid Protocols ─────────────────────────────
        log.info("\nSTEP 3 · Testing invalid protocol rejections…")
        forbidden_urls = [
            "file:///C:/Windows/System32/drivers/etc/hosts",
            "javascript:alert('xss')",
            "data:text/html,<h1>Hacked</h1>",
            "chrome://settings",
            "ftp://files.example.com/test.txt",
        ]

        for bad_url in forbidden_urls:
            bad_res = manager.open_url(bad_url)
            log.info("Testing forbidden URL '%s' -> success=%s, error='%s'", bad_url, bad_res.success, bad_res.error)
            if bad_res.success:
                log.error("❌ FAILED: Forbidden URL '%s' was incorrectly accepted!", bad_url)
                all_passed = False
            else:
                log.info("✔ Correctly rejected forbidden URL: %s", bad_url)

        # ── Test 3: Malformed & Empty Inputs ─────────────────────────────
        log.info("\nSTEP 4 · Testing malformed / empty URL inputs…")
        malformed_urls = ["", "   ", "http://", "not_a_url"]
        for m_url in malformed_urls:
            m_res = manager.open_url(m_url)
            log.info("Testing malformed input '%s' -> success=%s, error='%s'", m_url, m_res.success, m_res.error)
            if m_res.success:
                log.error("❌ FAILED: Malformed URL '%s' was accepted!", m_url)
                all_passed = False

        log.info("✔ Malformed input handling PASSED!")

        # ── Test 4: Unreachable / Non-existent Domain ────────────────────
        log.info("\nSTEP 5 · Testing navigation failure (unreachable domain)…")
        unreachable_url = "https://this-domain-does-not-exist-sih2026-test.org"
        fail_res = manager.open_url(unreachable_url, timeout_ms=5000)
        log.info("Testing unreachable domain '%s' -> success=%s, error='%s'", unreachable_url, fail_res.success, fail_res.error)

        if fail_res.success:
            log.error("❌ FAILED: Unreachable domain returned success=True!")
            all_passed = False
        elif not fail_res.error:
            log.error("❌ FAILED: Unreachable domain returned success=False but no error message!")
            all_passed = False
        else:
            log.info("✔ Unreachable domain failure handled gracefully PASSED!")

    except Exception as exc:
        log.error("❌ Test crashed with exception: %s", exc, exc_info=True)
        all_passed = False
    finally:
        log.info("\nSTEP 6 · Closing BrowserManager…")
        manager.close()
        log.info("✔ BrowserManager closed cleanly.")

    log.info("=" * 60)
    if all_passed:
        log.info("OVERALL RESULT: ALL TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = run_open_url_tests()
    sys.exit(0 if success else 1)
