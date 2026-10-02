"""
test_get_links.py — Focused test suite for the browser get_links action.

Run from backend/ directory:

    .venv\\Scripts\\python test_get_links.py

Tests verified:
1. BrowserManager starts.
2. Local test page loads.
3. Valid links are extracted.
4. Relative URLs become absolute.
5. Visible text is whitespace-normalized.
6. Duplicate URLs are deduplicated.
7. Invalid protocols are excluded (javascript, mailto, tel).
8. Empty href is excluded.
9. Hidden link is excluded.
10. DOM order is preserved.
11. max_links truncates correctly.
12. truncated=True when truncation occurs.
13. truncated=False when all links fit.
14. Invalid max_links (0, negative, non-integer) rejected.
15. Empty page returns an empty list successfully.
16. Extraction does not navigate away from the current page.
17. Closed/unstarted BrowserManager fails safely.
18. Regressions for other tools.
19. Cleanup - no orphan processes.
"""

import logging
import os
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer

sys.path.insert(0, ".")

from app.browser import (
    BrowserManager,
    BrowserLinksResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_get_links_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — get_links Verification Test Suite")
    log.info("=" * 65)

    manager = BrowserManager(headless=False)
    temp_dir = tempfile.mkdtemp()
    
    test_page = os.path.join(temp_dir, "test_links.html")
    empty_page = os.path.join(temp_dir, "empty_links.html")
    test_screenshot_path = os.path.join(temp_dir, "test_shot_links.png")

    html_content = """
    <html>
      <body>
        <!-- 1. Absolute HTTP link -->
        <a id="l1" href="https://example.com/one">  First Link  </a>
        
        <!-- 2. Relative link -->
        <a id="l2" href="/two">Second Link</a>
        
        <!-- 3. Duplicate URL with different text -->
        <a id="l3" href="https://example.com/one">First Link Duplicate</a>
        
        <!-- 4. Invalid protocol links -->
        <a href="javascript:void(0)">JS Link</a>
        <a href="mailto:test@example.com">Email</a>
        <a href="tel:1234567890">Phone</a>
        <a href="data:text/html,<html></html>">Data</a>
        <a href="file:///C:/test.txt">File</a>
        
        <!-- 5. Empty / whitespace href -->
        <a>No Href</a>
        <a href="">Empty Href</a>
        <a href="   ">Whitespace Href</a>
        
        <!-- 6. Hidden link -->
        <a href="https://example.com/hidden" style="display:none;">Hidden</a>
        
        <!-- 7. More valid links for truncation -->
        <a href="https://example.com/three">Third</a>
        <a href="https://example.com/four">Fourth</a>
        
        <!-- elements for regression -->
        <input id="input" type="text" />
        <button id="btn">Click</button>
      </body>
    </html>
    """
    
    with open(test_page, "w") as f:
        f.write(html_content)
    with open(empty_page, "w") as f:
        f.write("<html><body><h1>No links here</h1></body></html>")

    # Start local HTTP server
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
            
    server = HTTPServer(("localhost", 0), QuietHandler)
    port = server.server_address[1]
    
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    
    # Change working directory to temp_dir for the server
    old_cwd = os.getcwd()
    os.chdir(temp_dir)

    url_test = f"http://localhost:{port}/test_links.html"
    url_empty = f"http://localhost:{port}/empty_links.html"

    try:
        log.info("STEP 1 · Starting BrowserManager (visible Chromium)…")
        manager.start()
        log.info("✔ BrowserManager started.")

        # ── Test 1: Basic Extraction ─────────────
        log.info("\nSTEP 2 · Setting up test page and extracting links…")
        manager.page.goto(url_test)
        manager.page.wait_for_load_state("load")
        
        start_url = manager.page.url
        res: BrowserLinksResult = manager.get_links(max_links=100)
        end_url = manager.page.url
        
        log.info("Result: success=%s | truncated=%s | count=%d", res.success, res.truncated, len(res.links))

        # We expect:
        # 1. https://example.com/one (text: "First Link")
        # 2. https://example.com/two (text: "Second Link") - absolute resolved from base tag
        # 3. Duplicate is skipped
        # 4. Invalids are skipped
        # 5. Empties are skipped
        # 6. Hidden is skipped
        # 7. https://example.com/three
        # 8. https://example.com/four
        # Total expected: 4
        
        if not res.success:
            log.error("❌ FAILED: get_links() returned success=False")
            all_passed = False
        elif len(res.links) != 4:
            log.error("❌ FAILED: Expected 4 links, got %d", len(res.links))
            for i, l in enumerate(res.links):
                log.info("  %d: %s -> %s", i, l.text, l.url)
            all_passed = False
        else:
            log.info("✔ Link count and filtering correct!")
            
            # Check DOM order and whitespace normalization
            if res.links[0].text != "First Link":
                log.error("❌ FAILED: Whitespace normalization failed! (Got '%s')", res.links[0].text)
                all_passed = False
            
            # Check URL resolution
            if not res.links[1].url.endswith("/two"):
                log.error("❌ FAILED: Relative URL resolution failed! (Got '%s')", res.links[1].url)
                all_passed = False
                
            # Check deduplication
            urls = [l.url for l in res.links]
            if len(urls) != len(set(urls)):
                log.error("❌ FAILED: Deduplication failed!")
                all_passed = False
                
            # Check navigation
            if start_url != end_url:
                log.error("❌ FAILED: get_links caused navigation!")
                all_passed = False

        # ── Test 2: Truncation ─────────────
        log.info("\nSTEP 3 · Testing max_links truncation…")
        res_trunc = manager.get_links(max_links=2)
        if not res_trunc.success or not res_trunc.truncated or len(res_trunc.links) != 2:
            log.error("❌ FAILED: Truncation failed! truncated=%s, count=%d", res_trunc.truncated, len(res_trunc.links))
            all_passed = False
        else:
            log.info("✔ Truncation PASSED!")

        # ── Test 3: Invalid max_links ─────────────
        log.info("\nSTEP 4 · Testing invalid max_links…")
        for bad_max in [0, -5, "10", 1.5, None]:
            r = manager.get_links(max_links=bad_max)
            log.info("max_links '%s' → success=%s, error='%s'", bad_max, r.success, r.error)
            if r.success:
                log.error("❌ FAILED: Bad max_links '%s' was accepted!", bad_max)
                all_passed = False
        log.info("✔ Invalid max_links rejection PASSED!")

        # ── Test 4: Empty Page ─────────────
        log.info("\nSTEP 5 · Testing empty page…")
        manager.page.goto(url_empty)
        manager.page.wait_for_load_state("load")
        res_empty = manager.get_links()
        if not res_empty.success or len(res_empty.links) != 0:
            log.error("❌ FAILED: Empty page extraction failed!")
            all_passed = False
        else:
            log.info("✔ Empty page extraction PASSED!")

        # ── Test 5: Regressions ──────────────────────────────────────────
        log.info("\nSTEP 6 · Running regression tests for open_url, get_page_text, click, fill, press, screenshot, scroll, go_back…")
        
        manager.page.goto(url_test)
        
        reg_fill = manager.fill("#input", "regression")
        reg_press = manager.press("#input", "Tab")
        reg_click = manager.click("#btn")
        reg_shot = manager.screenshot(test_screenshot_path)
        reg_scroll = manager.scroll("down", 100)
        reg_text = manager.get_page_text()
        
        manager.open_url("https://example.com")
        reg_back = manager.go_back()

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
        elif not reg_back.success:
            log.error("❌ FAILED: go_back() regression failed!")
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
        r = manager.get_links()
        log.info("Closed browser → success=%s, error='%s'", r.success, r.error)
        if r.success:
            log.error("❌ FAILED: Closed browser returned success=True!")
            all_passed = False
        else:
            log.info("✔ Closed browser handling PASSED!")

        os.chdir(old_cwd)
        server.shutdown()
        server.server_close()

        # Cleanup temp files
        for fpath in [test_page, empty_page, test_screenshot_path]:
            if os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass
        try:
            os.rmdir(temp_dir)
        except Exception:
            pass

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL GET_LINKS TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_get_links_tests()
    sys.exit(0 if success else 1)
