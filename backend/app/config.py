"""
Configuration management for the AI Browser Agent.
Handles loading environment variables securely using python-dotenv.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Automatically search for and load .env file
load_dotenv()


class LLMConfigurationError(Exception):
    """Raised when required LLM configuration is missing or invalid."""
    pass


class Config:
    """
    Application configuration helper.
    Ensures environment variables like API keys are accessed securely.
    """
    def __init__(self, env_file: Optional[str] = None):
        if env_file:
            load_dotenv(env_file, override=True)

    @property
    def gemini_api_key(self) -> Optional[str]:
        """Returns the Gemini API key from environment, or None if not set."""
        key = os.getenv("GEMINI_API_KEY")
        if key and key.strip():
            return key.strip()
        return None

    @property
    def gemini_model(self) -> str:
        """Returns the Gemini model name from environment, defaulting to 'gemini-2.5-flash'."""
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        if not model or not model.strip():
            return "gemini-2.5-flash"
        return model.strip()

    def get_required_gemini_api_key(self) -> str:
        """
        Retrieves the Gemini API key.
        Raises LLMConfigurationError if the key is not set or empty.
        Secret is never included in the exception message.
        """
        key = self.gemini_api_key
        if not key:
            raise LLMConfigurationError(
                "GEMINI_API_KEY environment variable is missing or empty. "
                "Please set GEMINI_API_KEY in your environment or .env file."
            )
        return key

    def __repr__(self) -> str:
        key_status = "SET" if self.gemini_api_key else "NOT_SET"
        return f"Config(gemini_model='{self.gemini_model}', gemini_api_key=[{key_status}])"


# Default global instance
config = Config()
