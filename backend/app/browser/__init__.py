"""
browser package — Browser automation primitives for AI Browser Agent backend.
"""

from app.browser.actions import click, fill, get_page_text, go_back, open_url, press, screenshot, scroll, get_links
from app.browser.manager import BrowserManager
from app.browser.schema import (
    BrowserActionResult,
    BrowserClickResult,
    BrowserFillResult,
    BrowserPageTextResult,
    BrowserPressResult,
    BrowserScreenshotResult,
    BrowserScrollResult,
    BrowserGoBackResult,
    BrowserLink,
    BrowserLinksResult,
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
    "go_back",
    "get_links",
    "BrowserActionResult",
    "BrowserPageTextResult",
    "BrowserClickResult",
    "BrowserFillResult",
    "BrowserPressResult",
    "BrowserScreenshotResult",
    "BrowserScrollResult",
    "BrowserGoBackResult",
    "BrowserLink",
    "BrowserLinksResult",
]
