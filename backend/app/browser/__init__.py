"""
browser package — Browser automation primitives for AI Browser Agent backend.
"""

from app.browser.actions import click, fill, get_page_text, open_url
from app.browser.manager import BrowserManager
from app.browser.schema import (
    BrowserActionResult,
    BrowserClickResult,
    BrowserFillResult,
    BrowserPageTextResult,
)

__all__ = [
    "BrowserManager",
    "open_url",
    "get_page_text",
    "click",
    "fill",
    "BrowserActionResult",
    "BrowserPageTextResult",
    "BrowserClickResult",
    "BrowserFillResult",
]
