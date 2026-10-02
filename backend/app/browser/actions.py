"""
browser/actions.py — Core browser actions.

Currently provides:
- open_url: Navigates to a validated HTTP/HTTPS URL and returns a BrowserActionResult.
"""

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.browser.schema import BrowserActionResult

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}


def open_url(page: "Page", url: str, timeout_ms: int = 30000) -> BrowserActionResult:
    """
    Navigate the given Playwright Page to a URL.

    Validation rules:
    - URL must be a non-empty string.
    - Protocol MUST be 'http' or 'https' (blocks file://, javascript:, data:, chrome://, etc.).
    - Network location (netloc) must be present.

    Returns:
    - BrowserActionResult with success, resolved url, title, and optional error message.
    """
    if not url or not isinstance(url, str):
        return BrowserActionResult(
            success=False,
            url=str(url) if url is not None else "",
            error="URL must be a non-empty string.",
        )

    raw_url = url.strip()

    try:
        parsed = urlparse(raw_url)
    except Exception as exc:
        return BrowserActionResult(
            success=False,
            url=raw_url,
            error=f"Malformed URL: {exc}",
        )

    scheme = parsed.scheme.lower() if parsed.scheme else ""

    if scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        return BrowserActionResult(
            success=False,
            url=raw_url,
            error=f"Invalid URL protocol or format '{raw_url}'. Only http:// and https:// URLs are allowed.",
        )

    try:
        logger.info("Navigating to URL: %s", raw_url)
        page.goto(raw_url, timeout=timeout_ms, wait_until="domcontentloaded")
        page_title = page.title()
        final_url = page.url

        logger.info("Successfully navigated to '%s' (title: '%s')", final_url, page_title)
        return BrowserActionResult(
            success=True,
            url=final_url,
            title=page_title,
            error=None,
        )
    except Exception as exc:
        logger.warning("Navigation failed for '%s': %s", raw_url, exc)
        return BrowserActionResult(
            success=False,
            url=raw_url,
            title=None,
            error=f"Navigation failed: {exc}",
        )
