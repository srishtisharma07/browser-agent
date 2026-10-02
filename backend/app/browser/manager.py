"""
browser/manager.py — Playwright browser lifecycle management.

Responsibilities
----------------
* Start Playwright (sync API via a dedicated thread wrapper)
* Launch a VISIBLE Chromium browser (headless=False, for SIH demo purposes)
* Create a BrowserContext and a single Page
* Tear everything down cleanly so no orphaned Chromium processes remain

What this module does NOT do
-----------------------------
* No navigation / clicking / typing
* No screenshots
* No agent tool calls
* No WebSocket streaming
* No AI / LangGraph integration

Those capabilities will be layered on top in later phases.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
)

from app.browser.actions import click as execute_click
from app.browser.actions import fill as execute_fill
from app.browser.actions import get_page_text as execute_get_page_text
from app.browser.actions import open_url as execute_open_url
from app.browser.actions import press as execute_press
from app.browser.actions import screenshot as execute_screenshot
from app.browser.actions import scroll as execute_scroll
from app.browser.actions import go_back as execute_go_back
from app.browser.actions import get_links as execute_get_links
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

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Manages the full lifecycle of one Playwright + Chromium session.

    Usage
    -----
    manager = BrowserManager()
    manager.start()   # opens visible Chromium
    result = manager.open_url("https://example.com")
    manager.close()   # cleans up everything
    """

    def __init__(self, headless: bool = False) -> None:
        """
        Parameters
        ----------
        headless:
            Set to False (default) so Chromium is visible during development
            and the SIH demo.  Pass True only in CI/testing environments.
        """
        self.headless: bool = headless

        # Playwright runtime objects — all None until start() is called.
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────

    def start(self) -> None:
        """
        Start Playwright, launch Chromium, create a context and a blank page.

        Raises
        ------
        RuntimeError
            If the browser is already running.
        """
        with self._lock:
            if self._browser is not None:
                raise RuntimeError("BrowserManager is already running. Call close() first.")

            logger.info("Starting Playwright…")
            self._playwright = sync_playwright().start()

            logger.info("Launching Chromium (headless=%s)…", self.headless)
            self._browser = self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-blink-features=AutomationControlled",  # less bot-detectable
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )

            logger.info("Creating browser context…")
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )

            logger.info("Opening blank page…")
            self._page = self._context.new_page()

        logger.info("BrowserManager started successfully.")

    def close(self) -> None:
        """
        Close the page, context, browser, and Playwright runtime in order.
        Safe to call even if start() was never called.
        """
        with self._lock:
            self._close_unlocked()

    def open_url(self, url: str, timeout_ms: int = 30000) -> BrowserActionResult:
        """
        Navigate the active browser page to the specified HTTP/HTTPS URL.

        Returns a BrowserActionResult indicating success or failure.
        """
        if not self.is_running:
            return BrowserActionResult(
                success=False,
                url=url,
                error="Browser is not running. Call start() first.",
            )
        return execute_open_url(self.page, url, timeout_ms=timeout_ms)

    def get_page_text(self, max_length: int = 20000) -> BrowserPageTextResult:
        """
        Extract readable visible text content from the active browser page.

        Parameters:
        - max_length: Maximum allowed text character length (default: 20000).

        Returns a BrowserPageTextResult with success status, extracted text, url, truncation flag, or error.
        """
        if not self.is_running:
            return BrowserPageTextResult(
                success=False,
                url="",
                text=None,
                truncated=False,
                error="Browser is not running. Call start() first.",
            )
        return execute_get_page_text(self.page, max_length=max_length)

    def click(self, selector: str, timeout_ms: int = 30000) -> BrowserClickResult:
        """
        Click an element on the active page identified by selector.

        Parameters:
        - selector: Element CSS/text selector.
        - timeout_ms: Action timeout in milliseconds.

        Returns a BrowserClickResult indicating success or failure.
        """
        if not self.is_running:
            return BrowserClickResult(
                success=False,
                selector=selector,
                url="",
                error="Browser is not running. Call start() first.",
            )
        return execute_click(self.page, selector, timeout_ms=timeout_ms)

    def fill(
        self,
        selector: str,
        value: str,
        timeout_ms: int = 30000,
    ) -> BrowserFillResult:
        """
        Fill an input, textarea, or form field on the active page identified by selector.

        Parameters:
        - selector: Target form control selector.
        - value: Text string to fill into the input control.
        - timeout_ms: Action timeout in milliseconds.

        Returns a BrowserFillResult indicating success or failure.
        """
        if not self.is_running:
            return BrowserFillResult(
                success=False,
                selector=selector,
                url="",
                error="Browser is not running. Call start() first.",
            )
        return execute_fill(self.page, selector, value, timeout_ms=timeout_ms)

    def press(
        self,
        selector: str,
        key: str,
        timeout_ms: int = 30000,
    ) -> BrowserPressResult:
        """
        Send a keyboard key/combination to the element identified by selector.

        Parameters:
        - selector: Target element selector.
        - key: Playwright key name or combination (e.g. 'Enter', 'Tab', 'Control+A').
        - timeout_ms: Action timeout in milliseconds.

        Returns a BrowserPressResult indicating success or failure.
        """
        if not self.is_running:
            return BrowserPressResult(
                success=False,
                selector=selector,
                key=key,
                url="",
                error="Browser is not running. Call start() first.",
            )
        return execute_press(self.page, selector, key, timeout_ms=timeout_ms)

    def screenshot(
        self,
        path: str,
        timeout_ms: int = 30000,
    ) -> BrowserScreenshotResult:
        """
        Take a screenshot of the active page and save it to path.

        Parameters:
        - path: File path where the screenshot should be saved.
        - timeout_ms: Action timeout in milliseconds.

        Returns a BrowserScreenshotResult indicating success or failure.
        """
        if not self.is_running:
            return BrowserScreenshotResult(
                success=False,
                url="",
                image_path=None,
                error="Browser is not running. Call start() first.",
            )
        return execute_screenshot(self.page, path, timeout_ms=timeout_ms)

    def scroll(
        self,
        direction: str,
        amount: int = 800,
        timeout_ms: int = 30000,
    ) -> BrowserScrollResult:
        """
        Scroll the active page up or down.

        Parameters:
        - direction: 'up' or 'down'.
        - amount: Number of pixels to scroll (positive integer).
        - timeout_ms: Action timeout in milliseconds.

        Returns a BrowserScrollResult indicating success or failure.
        """
        if not self.is_running:
            return BrowserScrollResult(
                success=False,
                url="",
                error="Browser is not running. Call start() first.",
            )
        return execute_scroll(self.page, direction, amount=amount, timeout_ms=timeout_ms)

    def go_back(
        self,
        timeout_ms: int = 30000,
    ) -> BrowserGoBackResult:
        """
        Navigate to the previous page in browser history.

        Parameters:
        - timeout_ms: Action timeout in milliseconds.

        Returns a BrowserGoBackResult indicating success or failure.
        """
        if not self.is_running:
            return BrowserGoBackResult(
                success=False,
                url="",
                error="Browser is not running. Call start() first.",
            )
        return execute_go_back(self.page, timeout_ms=timeout_ms)

    def get_links(
        self,
        max_links: int = 100,
        timeout_ms: int = 30000,
    ) -> BrowserLinksResult:
        """
        Extract visible/usable links from the current page.

        Parameters:
        - max_links: Maximum number of links to extract.
        - timeout_ms: Action timeout in milliseconds.

        Returns a BrowserLinksResult indicating success or failure and containing the links.
        """
        if not self.is_running:
            return BrowserLinksResult(
                success=False,
                url="",
                links=[],
                truncated=False,
                error="Browser is not running. Call start() first.",
            )
        return execute_get_links(self.page, max_links=max_links, timeout_ms=timeout_ms)

    # ── Read-only accessors (raise if not started) ────────────────────

    @property
    def page(self) -> Page:
        """The active Playwright Page. Raises if the browser is not running."""
        if self._page is None:
            raise RuntimeError("Browser is not running. Call start() first.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        """The active BrowserContext. Raises if the browser is not running."""
        if self._context is None:
            raise RuntimeError("Browser is not running. Call start() first.")
        return self._context

    @property
    def is_running(self) -> bool:
        """True if the browser has been started and not yet closed."""
        return self._browser is not None

    # ── Context-manager support ───────────────────────────────────────

    def __enter__(self) -> "BrowserManager":
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Internal helpers ──────────────────────────────────────────────

    def _close_unlocked(self) -> None:
        """Tear-down without acquiring the lock (caller must hold it)."""
        if self._page is not None:
            try:
                self._page.close()
                logger.info("Page closed.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error closing page: %s", exc)
            finally:
                self._page = None

        if self._context is not None:
            try:
                self._context.close()
                logger.info("Browser context closed.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error closing context: %s", exc)
            finally:
                self._context = None

        if self._browser is not None:
            try:
                self._browser.close()
                logger.info("Chromium closed.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error closing browser: %s", exc)
            finally:
                self._browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
                logger.info("Playwright stopped.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error stopping Playwright: %s", exc)
            finally:
                self._playwright = None
