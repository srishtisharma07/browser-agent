import sys
import logging
import inspect
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from app.browser.observation import observe_page, BrowserObservation
from app.browser.manager import BrowserManager
from app.agent.tools import ToolRegistry

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def run_tests():
    all_passed = True
    
    manager = BrowserManager(headless=True)
    manager.start()
    
    # Create deterministic local pages
    test_dir = Path(__file__).parent / "test_pages"
    test_dir.mkdir(exist_ok=True)
    
    normal_path = test_dir / "normal.html"
    normal_path.write_text("<html><head><title>Normal</title></head><body><p>Some text</p><a id='link' href='normal.html'>link</a></body></html>")
    
    empty_path = test_dir / "empty.html"
    empty_path.write_text("<html><head><title>Empty</title></head><body></body></html>")
    
    normal_url = f"file:///{normal_path.absolute().as_posix()}"
    empty_url = f"file:///{empty_path.absolute().as_posix()}"
    
    # TEST 1: Normal page
    log.info("Test 1: Normal page")
    manager.page.goto(normal_url)
    obs1 = observe_page(manager.page)
    if not (obs1.success and obs1.title == "Normal" and obs1.page_has_content and obs1.text_length > 0):
        log.error("Test 1 failed: %s", obs1)
        all_passed = False
    
    # TEST 2: Empty page
    log.info("Test 2: Empty page")
    manager.page.goto(empty_url)
    obs2 = observe_page(manager.page)
    if not (obs2.success and obs2.title == "Empty" and not obs2.page_has_content and obs2.text_length == 0):
        log.error("Test 2 failed: %s", obs2)
        all_passed = False
    
    # TEST 4: open_url integration
    log.info("Test 4: open_url")
    # For open_url to work with file:///, it actually fails because of ALLOWED_SCHEMES, but let's test with http://example.com
    res4 = manager.open_url("http://example.com")
    if not res4.success or res4.observation is None or not res4.observation.success:
        log.error("Test 4 failed: %s", res4)
        all_passed = False
    
    # TEST 5: click integration
    log.info("Test 5: click")
    manager.page.goto(normal_url)
    res5 = manager.click("#link")
    if not res5.success or res5.observation is None or not res5.observation.success:
        log.error("Test 5 failed: %s", res5)
        all_passed = False
        
    # TEST 6: go_back integration
    log.info("Test 6: go_back")
    manager.page.goto(normal_url)
    manager.page.goto(empty_url)
    res6 = manager.go_back()
    if not res6.success or res6.observation is None or res6.observation.title != "Normal":
        log.error("Test 6 failed: %s", res6)
        all_passed = False
    
    # TEST 8: ToolRegistry
    log.info("Test 8: ToolRegistry")
    registry = ToolRegistry(manager)
    exec_res = registry.execute("open_url", {"url": "http://example.com"})
    if not exec_res.success or exec_res.observation is None:
        log.error("Test 8 failed: %s", exec_res)
        all_passed = False
        
    manager.close()
    
    # TEST 3: Closed browser
    log.info("Test 3: Closed browser")
    obs3 = observe_page(manager._page)
    if obs3.success or obs3.error is None:
        log.error("Test 3 failed: %s", obs3)
        all_passed = False
        
    # TEST 7: No arbitrary JS
    log.info("Test 7: No arbitrary JS")
    import app.browser.observation as obs_module
    code = inspect.getsource(obs_module)
    if ".evaluate(" in code or "eval(" in code or "exec(" in code:
        log.error("Test 7 failed: found arbitrary JS/eval in observation module")
        all_passed = False
        
    if all_passed:
        log.info("ALL TESTS PASSED")
    else:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
