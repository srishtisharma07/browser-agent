"""
browser/actions.py — Core browser actions.

Currently provides:
- open_url: Navigates to a validated HTTP/HTTPS URL and returns a BrowserActionResult.
"""

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.browser.schema import (
    BrowserActionResult,
    BrowserClickResult,
    BrowserFillResult,
    BrowserPageTextResult,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = {"http", "https"}
DEFAULT_MAX_TEXT_LENGTH = 20000


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


def get_page_text(
    page: "Page",
    max_length: int = DEFAULT_MAX_TEXT_LENGTH,
) -> BrowserPageTextResult:
    """
    Extract visible readable text content from the given Playwright Page body.

    Parameters:
    - page: Active Playwright Page instance.
    - max_length: Maximum allowed character length for extracted text (default: 20000).

    Returns:
    - BrowserPageTextResult with success, text, url, truncated flag, and error message.
    """
    if page is None:
        return BrowserPageTextResult(
            success=False,
            url="",
            text=None,
            truncated=False,
            error="No active Playwright page available.",
        )

    try:
        current_url = page.url or ""
    except Exception as exc:
        return BrowserPageTextResult(
            success=False,
            url="",
            text=None,
            truncated=False,
            error=f"Failed to access page URL: {exc}",
        )

    try:
        body_locator = page.locator("body")
        if body_locator.count() == 0:
            raw_text = page.inner_text("html") if page.locator("html").count() > 0 else ""
        else:
            raw_text = body_locator.inner_text()

        text_content = raw_text.strip() if raw_text else ""

        truncated = False
        if max_length > 0 and len(text_content) > max_length:
            text_content = text_content[:max_length]
            truncated = True

        return BrowserPageTextResult(
            success=True,
            url=current_url,
            text=text_content,
            truncated=truncated,
            error=None,
        )
    except Exception as exc:
        logger.warning("Failed to extract page text from '%s': %s", current_url, exc)
        return BrowserPageTextResult(
            success=False,
            url=current_url,
            text=None,
            truncated=False,
            error=f"Page text extraction failed: {exc}",
        )


def click(
    page: "Page",
    selector: str,
    timeout_ms: int = 30000,
) -> BrowserClickResult:
    """
    Click an element on the given Playwright Page using a controlled selector.

    Validation rules:
    - Selector must be a non-empty string.
    - Uses Playwright's locator(selector).click(timeout=timeout_ms).
    - Does NOT execute arbitrary JavaScript (no page.evaluate / eval).

    Returns:
    - BrowserClickResult with success, selector, resolved url, and error message.
    """
    if page is None:
        return BrowserClickResult(
            success=False,
            selector=selector if selector else "",
            url="",
            error="No active Playwright page available.",
        )

    if not selector or not isinstance(selector, str) or not selector.strip():
        return BrowserClickResult(
            success=False,
            selector=str(selector) if selector is not None else "",
            url=page.url if page else "",
            error="Selector must be a non-empty string.",
        )

    clean_selector = selector.strip()

    try:
        current_url = page.url or ""
    except Exception as exc:
        return BrowserClickResult(
            success=False,
            selector=clean_selector,
            url="",
            error=f"Failed to access page URL: {exc}",
        )

    try:
        logger.info("Clicking element with selector '%s'...", clean_selector)
        page.locator(clean_selector).click(timeout=timeout_ms)
        final_url = page.url or current_url

        logger.info("Successfully clicked element '%s' (url: '%s')", clean_selector, final_url)
        return BrowserClickResult(
            success=True,
            selector=clean_selector,
            url=final_url,
            error=None,
        )
    except Exception as exc:
        logger.warning("Click action failed for selector '%s': %s", clean_selector, exc)
        return BrowserClickResult(
            success=False,
            selector=clean_selector,
            url=current_url,
            error=f"Click action failed: {exc}",
        )


def fill(
    page: "Page",
    selector: str,
    value: str,
    timeout_ms: int = 30000,
) -> BrowserFillResult:
    """
    Fill an input, textarea, or form field on the given Playwright Page using a controlled selector.

    Validation rules:
    - Selector must be a non-empty string.
    - Value must be a valid string instance.
    - Uses Playwright's locator(selector).fill(value, timeout=timeout_ms).
    - Does NOT execute arbitrary JavaScript (no page.evaluate / eval).
    - Does NOT log sensitive field values.

    Returns:
    - BrowserFillResult with success, selector, resolved url, and error message.
    """
    if page is None:
        return BrowserFillResult(
            success=False,
            selector=selector if selector else "",
            url="",
            error="No active Playwright page available.",
        )

    if not selector or not isinstance(selector, str) or not selector.strip():
        return BrowserFillResult(
            success=False,
            selector=str(selector) if selector is not None else "",
            url=page.url if page else "",
            error="Selector must be a non-empty string.",
        )

    if value is None or not isinstance(value, str):
        return BrowserFillResult(
            success=False,
            selector=selector.strip(),
            url=page.url if page else "",
            error="Value must be a valid string instance.",
        )

    clean_selector = selector.strip()

    try:
        current_url = page.url or ""
    except Exception as exc:
        return BrowserFillResult(
            success=False,
            selector=clean_selector,
            url="",
            error=f"Failed to access page URL: {exc}",
        )

    try:
        logger.info("Filling element with selector '%s' (content length: %d)...", clean_selector, len(value))
        page.locator(clean_selector).fill(value, timeout=timeout_ms)
        final_url = page.url or current_url

        logger.info("Successfully filled element '%s' (url: '%s')", clean_selector, final_url)
        return BrowserFillResult(
            success=True,
            selector=clean_selector,
            url=final_url,
            error=None,
        )
    except Exception as exc:
        logger.warning("Fill action failed for selector '%s': %s", clean_selector, exc)
        return BrowserFillResult(
            success=False,
            selector=clean_selector,
            url=current_url,
            error=f"Fill action failed: {exc}",
        )



