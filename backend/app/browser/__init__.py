"""
browser package — Browser automation primitives for AI Browser Agent backend.
"""

from app.browser.actions import open_url
from app.browser.manager import BrowserManager
from app.browser.schema import BrowserActionResult

__all__ = ["BrowserManager", "open_url", "BrowserActionResult"]
