from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

@dataclass
class BrowserObservation:
    """Structured post-action browser state observation."""
    success: bool
    url: str
    title: Optional[str] = None
    page_has_content: bool = False
    text_length: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def observe_page(page: Any) -> BrowserObservation:
    """
    Safely determine the current structured browser state from a Playwright Page.
    Does NOT use JS injection.
    """
    if page is None:
        return BrowserObservation(
            success=False,
            url="",
            error="Browser page is not available or closed."
        )

    try:
        url = page.url or ""
    except Exception as exc:
        return BrowserObservation(
            success=False,
            url="",
            error=f"Failed to access page URL: {exc}"
        )

    try:
        if page.is_closed():
            return BrowserObservation(
                success=False,
                url=url,
                error="Browser page is closed."
            )
            
        title = page.title()
        
        # safely determine text length without evaluate
        body_locator = page.locator("body")
        if body_locator.count() > 0:
            text = body_locator.inner_text()
        else:
            html_locator = page.locator("html")
            if html_locator.count() > 0:
                text = page.inner_text("html")
            else:
                text = ""
                
        text_content = text.strip() if text else ""
        text_length = len(text_content)
        page_has_content = text_length > 0
        
        return BrowserObservation(
            success=True,
            url=url,
            title=title,
            page_has_content=page_has_content,
            text_length=text_length,
            error=None
        )
    except Exception as exc:
        return BrowserObservation(
            success=False,
            url=url,
            error=f"Observation failed: {exc}"
        )
