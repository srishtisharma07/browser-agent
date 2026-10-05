"""
Controlled Browser Tool Registry for AI Browser Agent.
Acts as a security and execution boundary between the LLM and the browser.
"""

import json
from typing import Any, Callable, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ValidationError

from app.browser.manager import BrowserManager

# --- Tool Input Schemas ---

class OpenUrlInput(BaseModel):
    url: str = Field(description="The HTTP or HTTPS URL to navigate to.")
    timeout_ms: int = Field(default=30000, description="Navigation timeout in milliseconds.")

class GetPageTextInput(BaseModel):
    max_length: int = Field(default=20000, description="Maximum characters to extract.")

class ClickInput(BaseModel):
    selector: str = Field(description="CSS or text selector for the element to click.")
    timeout_ms: int = Field(default=30000, description="Timeout in milliseconds.")

class FillInput(BaseModel):
    selector: str = Field(description="CSS or text selector for the input element.")
    value: str = Field(description="The text to fill into the input.")
    timeout_ms: int = Field(default=30000, description="Timeout in milliseconds.")

class PressInput(BaseModel):
    selector: str = Field(description="CSS or text selector for the element.")
    key: str = Field(description="The keyboard key to press (e.g., 'Enter', 'Tab').")
    timeout_ms: int = Field(default=30000, description="Timeout in milliseconds.")

class ScreenshotInput(BaseModel):
    path: str = Field(description="Absolute or relative file path to save the screenshot.")
    timeout_ms: int = Field(default=30000, description="Timeout in milliseconds.")

class ScrollInput(BaseModel):
    direction: Literal["up", "down"] = Field(description="Direction to scroll ('up' or 'down').")
    amount: int = Field(default=800, description="Amount to scroll in pixels.")
    timeout_ms: int = Field(default=30000, description="Timeout in milliseconds.")

class GoBackInput(BaseModel):
    timeout_ms: int = Field(default=30000, description="Timeout in milliseconds.")

class GetLinksInput(BaseModel):
    max_links: int = Field(default=100, description="Maximum number of links to extract.")
    timeout_ms: int = Field(default=30000, description="Timeout in milliseconds.")

class RecordResearchFindingInput(BaseModel):
    title: str = Field(description="Short title of the finding.")
    url: str = Field(description="URL of the source page.")
    summary: str = Field(description="Concise summary of the extracted information.")
    key_points: List[str] = Field(default_factory=list, description="Key factual points extracted.")
    source: str = Field(default="browser", description="Source type of this finding.")


# --- Tool Definition ---

class ToolDefinition:
    """Definition of an approved browser tool."""
    def __init__(self, name: str, description: str, input_model: type[BaseModel], executor: Callable):
        self.name = name
        self.description = description
        self.input_model = input_model
        self.executor = executor

    @property
    def input_schema(self) -> Dict[str, Any]:
        """Returns the JSON schema representation of the input parameters."""
        return self.input_model.model_json_schema()

    def get_schema(self) -> Dict[str, Any]:
        """Returns the full schema definition for LLM tool binding."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }


# --- Tool Registry ---

class ToolRegistry:
    """
    Registry for managing and safely executing approved browser tools.
    """
    def __init__(self, browser_manager: BrowserManager):
        self._manager = browser_manager
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()

    def register(self, tool: ToolDefinition) -> None:
        """Register a new tool. Rejects duplicates."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition:
        """Get a tool definition by exact name. Raises ValueError if unknown."""
        if name not in self._tools:
            raise ValueError(f"Unknown tool: '{name}'")
        return self._tools[name]

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return schemas for all registered tools, suitable for LLM APIs."""
        return [tool.get_schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """
        Safely execute a registered tool with provided arguments.
        Rejects unknown tools and invalid arguments before browser interaction.
        """
        tool = self.get(name)
        
        # Validate arguments using Pydantic
        try:
            validated_args = tool.input_model.model_validate(arguments)
        except ValidationError as e:
            # We wrap it in a generic dict response matching the tool's result style
            return {
                "success": False,
                "error": f"Invalid arguments for tool '{name}': {e}",
            }
            
        # Execute the registered callable with the validated arguments
        try:
            return tool.executor(**validated_args.model_dump())
        except Exception as e:
            return {
                "success": False,
                "error": f"Tool execution failed: {e}",
            }

    def _register_default_tools(self) -> None:
        """Registers the set of approved browser primitives."""
        self.register(ToolDefinition(
            name="open_url",
            description="Navigate the browser to an HTTP or HTTPS URL.",
            input_model=OpenUrlInput,
            executor=self._manager.open_url
        ))
        self.register(ToolDefinition(
            name="get_page_text",
            description="Extract readable text from the current page.",
            input_model=GetPageTextInput,
            executor=self._manager.get_page_text
        ))
        self.register(ToolDefinition(
            name="click",
            description="Click a page element using a controlled CSS or text selector.",
            input_model=ClickInput,
            executor=self._manager.click
        ))
        self.register(ToolDefinition(
            name="fill",
            description="Enter text into an input or textarea using a controlled selector.",
            input_model=FillInput,
            executor=self._manager.fill
        ))
        self.register(ToolDefinition(
            name="press",
            description="Send a controlled keyboard key or combination to a selected element.",
            input_model=PressInput,
            executor=self._manager.press
        ))
        self.register(ToolDefinition(
            name="screenshot",
            description="Capture a screenshot of the current page and save it to a local path.",
            input_model=ScreenshotInput,
            executor=self._manager.screenshot
        ))
        self.register(ToolDefinition(
            name="scroll",
            description="Scroll the current page up or down.",
            input_model=ScrollInput,
            executor=self._manager.scroll
        ))
        self.register(ToolDefinition(
            name="go_back",
            description="Navigate to the previous page in browser history.",
            input_model=GoBackInput,
            executor=self._manager.go_back
        ))
        self.register(ToolDefinition(
            name="get_links",
            description="Extract structured links from the current page.",
            input_model=GetLinksInput,
            executor=self._manager.get_links
        ))
        self.register(ToolDefinition(
            name="record_research_finding",
            description="Record structured research findings into the agent state.",
            input_model=RecordResearchFindingInput,
            executor=lambda **kwargs: {"success": True, "finding": kwargs}
        ))
