"""
browser package — Browser automation primitives for AI Browser Agent backend.
"""

from app.browser.actions import click, fill, get_page_text, open_url, press, screenshot, scroll
from app.browser.manager import BrowserManager
from app.browser.schema import (
    BrowserActionResult,
    BrowserClickResult,
    BrowserFillResult,
    BrowserPageTextResult,
    BrowserPressResult,
    BrowserScreenshotResult,
    BrowserScrollResult,
)

__all__ = [
    "BrowserManager",
    "open_url",
    "get_page_text",
    "click",
    "fill",
    "press",
    "screenshot",
    "scroll",
    "BrowserActionResult",
    "BrowserPageTextResult",
    "BrowserClickResult",
    "BrowserFillResult",
    "BrowserPressResult",
    "BrowserScreenshotResult",
    "BrowserScrollResult",
]
