"""
Abstract LLM Provider interface and response models.
Ensures the agent is decoupled from any specific LLM SDK or vendor.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LLMToolCall(BaseModel):
    """Represents a tool/function call requested by the LLM."""
    name: str = Field(description="Name of the tool to execute.")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Argument values for the tool.")


class LLMResponse(BaseModel):
    """
    Standardized response object returned by an LLM provider.
    Does NOT leak internal SDK types to the rest of the application.
    """
    text: Optional[str] = Field(default=None, description="Generated text response from the model.")
    tool_calls: List[LLMToolCall] = Field(default_factory=list, description="Tool calls requested by the model.")
    finish_reason: Optional[str] = Field(default=None, description="Completion finish reason.")
    raw_response: Optional[Any] = Field(default=None, exclude=True, description="Raw provider response object (excluded from serialization).")
    error: Optional[str] = Field(default=None, description="Error message if the call failed.")

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """
    Abstract base interface for LLM providers.
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> LLMResponse:
        """
        Generate text or tool calls for a given prompt.

        Args:
            prompt: User or task prompt.
            tools: Optional list of tool JSON schemas (e.g. from ToolRegistry.get_tool_schemas()).
            system_instruction: Optional system instruction prompt.

        Returns:
            LLMResponse object containing text, tool_calls, or error.
        """
        pass
