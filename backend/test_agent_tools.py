"""
test_agent_tools.py — Focused test suite for the browser tool registry.

Run from backend/ directory:

    .venv\\Scripts\\python test_agent_tools.py
"""

import json
import logging
import os
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer

sys.path.insert(0, ".")

from app.browser.manager import BrowserManager
from app.agent.tools import ToolRegistry, ToolDefinition, OpenUrlInput

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_tools_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — ToolRegistry Verification Test Suite")
    log.info("=" * 65)

    manager = BrowserManager(headless=False)
    
    # ── Test 1: Initialization & Registration ─────────────
    log.info("STEP 1 · Testing ToolRegistry initialization…")
    registry = ToolRegistry(manager)
    
    # 1. Registry initializes with all 9 approved tools
    # 2. list_tools() returns expected tools
    expected_tools = ["open_url", "get_page_text", "click", "fill", "press", "screenshot", "scroll", "go_back", "get_links"]
    tools = registry.list_tools()
    if sorted(tools) != sorted(expected_tools):
        log.error("❌ FAILED: Missing tools or unexpected tools in registry: %s", tools)
        all_passed = False
        
    # 3. has("open_url") returns true
    if not registry.has("open_url"):
        log.error("❌ FAILED: has('open_url') returned False")
        all_passed = False
        
    # 4. has("nonexistent") returns false
    if registry.has("nonexistent"):
        log.error("❌ FAILED: has('nonexistent') returned True")
        all_passed = False
        
    # 5. get("open_url") returns correct definition
    open_url_def = registry.get("open_url")
    if not isinstance(open_url_def, ToolDefinition) or open_url_def.name != "open_url":
        log.error("❌ FAILED: get('open_url') returned incorrect definition")
        all_passed = False
        
    # 6. Unknown tool lookup fails clearly
    try:
        registry.get("nonexistent")
        log.error("❌ FAILED: get('nonexistent') did not raise ValueError")
        all_passed = False
    except ValueError:
        pass
        
    # 7. Duplicate registration fails clearly
    try:
        registry.register(ToolDefinition(name="open_url", description="Duplicate", input_model=OpenUrlInput, executor=lambda: None))
        log.error("❌ FAILED: Duplicate registration did not raise ValueError")
        all_passed = False
    except ValueError:
        pass
        
    # 8. Tool schemas are serializable
    # 9. get_tool_schemas() returns valid JSON-compatible data
    try:
        schemas = registry.get_tool_schemas()
        json.dumps(schemas) # Test serialization
        if len(schemas) != 9 or schemas[0]["name"] != "open_url":
            log.error("❌ FAILED: get_tool_schemas() returned invalid data")
            all_passed = False
    except Exception as exc:
        log.error("❌ FAILED: get_tool_schemas() raised exception: %s", exc)
        all_passed = False
        
    log.info("✔ Registry initialization, methods, and schema validation PASSED!")

    # ── Test 2: Controlled Execution & Arguments ─────────────
    log.info("\nSTEP 2 · Testing argument validation and controlled execution boundary…")
    
    # 19. Invalid tool arguments are rejected before browser execution
    res_invalid_args = registry.execute("open_url", {"url": 12345}) # URL must be string
    if res_invalid_args.get("success") is not False or "Invalid arguments" not in res_invalid_args.get("error", ""):
        log.error("❌ FAILED: Invalid arguments were not rejected correctly: %s", res_invalid_args)
        all_passed = False
        
    # 20. Unknown tools cannot execute
    try:
        registry.execute("nonexistent", {})
        log.error("❌ FAILED: Unknown tool execution did not raise ValueError")
        all_passed = False
    except ValueError:
        pass
        
    log.info("✔ Safety boundaries (argument rejection, unknown execution) PASSED!")


    # ── Test 3: Browser Interaction ─────────────
    log.info("\nSTEP 3 · Testing execution through BrowserManager…")
    
    temp_dir = tempfile.mkdtemp()
    test_page = os.path.join(temp_dir, "test_tools.html")
    test_screenshot_path = os.path.join(temp_dir, "test_shot_registry.png")
    
    with open(test_page, "w") as f:
        f.write("<html><body><h1>Test</h1><input id='inp' type='text'/><button id='btn'>Click</button><a href='/test'>Link</a></body></html>")
        
    # Use HTTP Server
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args): pass
    server = HTTPServer(("localhost", 0), QuietHandler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    old_cwd = os.getcwd()
    os.chdir(temp_dir)
    
    url = f"http://localhost:{port}/test_tools.html"
    
    try:
        manager.start()
        
        # 10. open_url executes through the registry
        res_open = registry.execute("open_url", {"url": url})
        if not hasattr(res_open, "success") or not res_open.success:
            log.error("❌ FAILED: execute(open_url) failed: %s", res_open)
            all_passed = False
            
        # 11. get_page_text executes
        res_text = registry.execute("get_page_text", {})
        if not res_text.success:
            log.error("❌ FAILED: execute(get_page_text) failed")
            all_passed = False
            
        # 12. click executes
        res_click = registry.execute("click", {"selector": "#btn"})
        if not res_click.success:
            log.error("❌ FAILED: execute(click) failed")
            all_passed = False
            
        # 13. fill executes
        res_fill = registry.execute("fill", {"selector": "#inp", "value": "test"})
        if not res_fill.success:
            log.error("❌ FAILED: execute(fill) failed")
            all_passed = False
            
        # 14. press executes
        res_press = registry.execute("press", {"selector": "#inp", "key": "Enter"})
        if not res_press.success:
            log.error("❌ FAILED: execute(press) failed")
            all_passed = False
            
        # 15. screenshot executes
        res_shot = registry.execute("screenshot", {"path": test_screenshot_path})
        if not res_shot.success:
            log.error("❌ FAILED: execute(screenshot) failed")
            all_passed = False
            
        # 16. scroll executes
        res_scroll = registry.execute("scroll", {"direction": "down", "amount": 100})
        if not res_scroll.success:
            log.error("❌ FAILED: execute(scroll) failed")
            all_passed = False
            
        # 18. get_links executes
        res_links = registry.execute("get_links", {})
        if not res_links.success:
            log.error("❌ FAILED: execute(get_links) failed")
            all_passed = False
            
        # 17. go_back executes
        res_open2 = registry.execute("open_url", {"url": "https://example.com"})
        res_back = registry.execute("go_back", {})
        if not res_back.success:
            log.error("❌ FAILED: execute(go_back) failed")
            all_passed = False
            
        log.info("✔ All tool executions PASSED!")
        
    except Exception as exc:
        log.error("❌ Test suite crashed: %s", exc, exc_info=True)
        all_passed = False
    finally:
        manager.close()
        os.chdir(old_cwd)
        server.shutdown()
        server.server_close()
        for fpath in [test_page, test_screenshot_path]:
            if os.path.exists(fpath):
                try: os.remove(fpath)
                except Exception: pass
        try: os.rmdir(temp_dir)
        except Exception: pass

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL TOOL REGISTRY TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_tools_tests()
    sys.exit(0 if success else 1)
