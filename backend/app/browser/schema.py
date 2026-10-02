"""
browser/schema.py — Typed schemas for browser action results.
"""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class BrowserActionResult:
    """Standardized result schema for general browser operations."""

    success: bool
    url: str
    title: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a plain dictionary for API responses or logs."""
        return asdict(self)


@dataclass
class BrowserPageTextResult:
    """Result schema for page text extraction operations."""

    success: bool
    url: str
    text: Optional[str] = None
    truncated: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a plain dictionary for API responses or logs."""
        return asdict(self)


@dataclass
class BrowserClickResult:
    """Result schema for click operations."""

    success: bool
    selector: str
    url: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a plain dictionary for API responses or logs."""
        return asdict(self)


@dataclass
class BrowserFillResult:
    """Result schema for fill/input operations."""

    success: bool
    selector: str
    url: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a plain dictionary for API responses or logs."""
        return asdict(self)


@dataclass
class BrowserPressResult:
    """Result schema for keyboard press operations."""

    success: bool
    selector: str
    key: str
    url: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a plain dictionary for API responses or logs."""
        return asdict(self)


@dataclass
class BrowserScreenshotResult:
    """Result schema for screenshot operations."""

    success: bool
    url: str
    image_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a plain dictionary for API responses or logs."""
        return asdict(self)


@dataclass
class BrowserScrollResult:
    """Result schema for scroll operations."""

    success: bool
    url: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a plain dictionary for API responses or logs."""
        return asdict(self)


@dataclass
class BrowserGoBackResult:
    """Result schema for back navigation operations."""

    success: bool
    url: str
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a plain dictionary for API responses or logs."""
        return asdict(self)


