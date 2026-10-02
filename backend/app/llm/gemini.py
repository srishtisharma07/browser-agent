"""
Gemini LLM Provider implementation using the official google-genai SDK.
Wraps Gemini API interactions in a clean, typed abstraction with strict secret isolation.
"""

import logging
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types

from app.config import config, LLMConfigurationError
from app.llm.provider import LLMProvider, LLMResponse, LLMToolCall

logger = logging.getLogger(__name__)


class GeminiLLMProvider(LLMProvider):
    """
    Concrete LLM provider using Google Gemini API.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Any] = None,
    ):
        """
        Initialize the Gemini LLM Provider.

        Args:
            api_key: Optional explicit Gemini API key. If omitted, loaded securely from Config.
            model: Optional model name. If omitted, loaded from Config (default: gemini-2.5-flash).
            client: Optional mock or pre-configured Client instance for testing.
        """
        # Determine API key
        if api_key is not None:
            if not api_key.strip():
                raise LLMConfigurationError("Provided API key is empty.")
            self.api_key = api_key.strip()
        else:
            self.api_key = config.get_required_gemini_api_key()

        # Determine model name
        if model is not None:
            if not model.strip():
                raise ValueError("Model name cannot be empty.")
            self.model = model.strip()
        else:
            self.model = config.gemini_model

        # Client initialization
        if client is not None:
            self.client = client
        else:
            self.client = genai.Client(api_key=self.api_key)

    def generate(
        self,
        prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> LLMResponse:
        """
        Generate response from Gemini model.

        Args:
            prompt: User prompt text.
            tools: Optional tool schemas (e.g. from ToolRegistry.get_tool_schemas()).
            system_instruction: Optional system prompt.

        Returns:
            LLMResponse object with generated text, tool calls, or error.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        try:
            # Build GenerateContentConfig options
            config_kwargs: Dict[str, Any] = {}

            if system_instruction and system_instruction.strip():
                config_kwargs["system_instruction"] = system_instruction.strip()

            if tools:
                # Convert tool schemas into Gemini FunctionDeclarations if needed
                function_declarations = []
                for tool in tools:
                    # If it's a dict with name, description, parameters
                    fd = types.FunctionDeclaration(
                        name=tool["name"],
                        description=tool.get("description", ""),
                        parameters=tool.get("parameters"),
                    )
                    function_declarations.append(fd)

                gemini_tool = types.Tool(function_declarations=function_declarations)
                config_kwargs["tools"] = [gemini_tool]

            gen_config = types.GenerateContentConfig(**config_kwargs) if config_kwargs else None

            # Call Gemini API
            if gen_config:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=gen_config,
                )
            else:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                )

            # Parse text response
            text = None
            try:
                text = response.text
            except Exception:
                text = None

            # Parse tool / function calls
            tool_calls: List[LLMToolCall] = []

            # Method 1: Check top-level response.function_calls if present
            raw_function_calls = getattr(response, "function_calls", None)
            if raw_function_calls:
                for fn_call in raw_function_calls:
                    name = getattr(fn_call, "name", None)
                    args = getattr(fn_call, "args", {})
                    if name:
                        tool_calls.append(LLMToolCall(
                            name=name,
                            arguments=dict(args) if isinstance(args, dict) else args
                        ))
            
            # Method 2: Check candidate content parts if function_calls was empty
            if not tool_calls and hasattr(response, "candidates") and response.candidates:
                for candidate in response.candidates:
                    content = getattr(candidate, "content", None)
                    if content and hasattr(content, "parts") and content.parts:
                        for part in content.parts:
                            fn_call = getattr(part, "function_call", None)
                            if fn_call:
                                name = getattr(fn_call, "name", None)
                                args = getattr(fn_call, "args", {})
                                if name:
                                    tool_calls.append(LLMToolCall(
                                        name=name,
                                        arguments=dict(args) if isinstance(args, dict) else args
                                    ))

            return LLMResponse(
                text=text,
                tool_calls=tool_calls,
                raw_response=response,
            )

        except Exception as e:
            # Sanitize error to prevent key leakage
            err_msg = str(e)
            if self.api_key in err_msg:
                err_msg = err_msg.replace(self.api_key, "[REDACTED]")
            logger.error("Gemini API call failed: %s", err_msg)
            return LLMResponse(error=f"Gemini API failure: {err_msg}")
