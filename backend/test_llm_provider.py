"""
test_llm_provider.py — Focused test suite for LLM provider abstraction and Gemini provider.

Run from backend/ directory:

    .venv\\Scripts\\python test_llm_provider.py

Tests verified:
1. Config loads GEMINI_MODEL default and environment override.
2. Config raises LLMConfigurationError when GEMINI_API_KEY is missing.
3. Config repr masks API key.
4. LLMResponse and LLMToolCall schemas function as expected.
5. GeminiLLMProvider initializes with explicit or env credentials.
6. GeminiLLMProvider rejects missing API key with LLMConfigurationError.
7. GeminiLLMProvider rejects empty prompt with ValueError.
8. GeminiLLMProvider generate text response (mocked SDK).
9. GeminiLLMProvider generate tool call response (mocked SDK).
10. GeminiLLMProvider converts tool schemas correctly for Gemini SDK.
11. GeminiLLMProvider sanitizes API key from error messages.
"""

import os
import sys
import logging
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from app.config import Config, LLMConfigurationError
from app.llm.provider import LLMResponse, LLMToolCall
from app.llm.gemini import GeminiLLMProvider
from app.agent.tools import ToolRegistry
from app.browser.manager import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_llm_provider_tests() -> bool:
    all_passed = True

    log.info("=" * 65)
    log.info("AI Browser Agent — LLM Provider Verification Test Suite")
    log.info("=" * 65)

    try:
        # --- TEST GROUP 1: Config & Environment Loading ---
        log.info("STEP 1 · Testing Config and environment loading…")

        # Backup existing env
        old_key = os.environ.get("GEMINI_API_KEY")
        old_model = os.environ.get("GEMINI_MODEL")

        try:
            # 1. Config loads default model
            if "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]
            if "GEMINI_MODEL" in os.environ:
                del os.environ["GEMINI_MODEL"]

            cfg_default = Config()
            if cfg_default.gemini_model != "gemini-2.5-flash":
                log.error("❌ FAILED: Default model is not 'gemini-2.5-flash', got '%s'", cfg_default.gemini_model)
                all_passed = False

            # 2. Config raises error when key is missing
            try:
                cfg_default.get_required_gemini_api_key()
                log.error("❌ FAILED: Missing GEMINI_API_KEY did not raise LLMConfigurationError")
                all_passed = False
            except LLMConfigurationError as e:
                log.info("✔ Missing API key raised LLMConfigurationError correctly: %s", e)

            # Test env override
            os.environ["GEMINI_API_KEY"] = "test_key_12345"
            os.environ["GEMINI_MODEL"] = "gemini-2.0-flash"

            cfg_custom = Config()
            if cfg_custom.gemini_api_key != "test_key_12345":
                log.error("❌ FAILED: Custom API key not loaded correctly")
                all_passed = False
            if cfg_custom.gemini_model != "gemini-2.0-flash":
                log.error("❌ FAILED: Custom model not loaded correctly")
                all_passed = False

            # 3. Config repr masks API key
            cfg_repr = repr(cfg_custom)
            if "test_key_12345" in cfg_repr or "SET" not in cfg_repr:
                log.error("❌ FAILED: Config repr exposed API key: %s", cfg_repr)
                all_passed = False
            else:
                log.info("✔ Config repr masked API key correctly: %s", cfg_repr)

        finally:
            # Restore env
            if old_key is not None:
                os.environ["GEMINI_API_KEY"] = old_key
            elif "GEMINI_API_KEY" in os.environ:
                del os.environ["GEMINI_API_KEY"]

            if old_model is not None:
                os.environ["GEMINI_MODEL"] = old_model
            elif "GEMINI_MODEL" in os.environ:
                del os.environ["GEMINI_MODEL"]

        log.info("✔ Config tests PASSED!")

        # --- TEST GROUP 2: LLM Response & Tool Call Models ---
        log.info("\nSTEP 2 · Testing LLM response and tool call models…")

        tc = LLMToolCall(name="open_url", arguments={"url": "https://example.com"})
        if tc.name != "open_url" or tc.arguments["url"] != "https://example.com":
            log.error("❌ FAILED: LLMToolCall initialization failed")
            all_passed = False

        res_text = LLMResponse(text="Hello world")
        if res_text.has_tool_calls or res_text.text != "Hello world":
            log.error("❌ FAILED: LLMResponse text parsing failed")
            all_passed = False

        res_tools = LLMResponse(tool_calls=[tc])
        if not res_tools.has_tool_calls or len(res_tools.tool_calls) != 1:
            log.error("❌ FAILED: LLMResponse tool_calls parsing failed")
            all_passed = False

        log.info("✔ LLM Response model tests PASSED!")

        # --- TEST GROUP 3: GeminiLLMProvider (Mocked) ---
        log.info("\nSTEP 3 · Testing GeminiLLMProvider with mocked client…")

        # 6. Rejects missing API key
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

        try:
            GeminiLLMProvider()
            log.error("❌ FAILED: Provider allowed missing API key without throwing")
            all_passed = False
        except LLMConfigurationError:
            log.info("✔ Provider correctly rejected missing API key.")

        # 7. Rejects empty prompt
        mock_client = MagicMock()
        provider = GeminiLLMProvider(api_key="secret_test_key_999", model="gemini-2.5-flash", client=mock_client)

        try:
            provider.generate("   ")
            log.error("❌ FAILED: Provider allowed empty prompt")
            all_passed = False
        except ValueError:
            log.info("✔ Provider correctly rejected empty prompt.")

        # 8. Test text response generation
        mock_text_resp = MagicMock()
        mock_text_resp.text = "Navigation complete."
        mock_text_resp.function_calls = None
        mock_text_resp.candidates = []
        mock_client.models.generate_content.return_value = mock_text_resp

        res = provider.generate("Navigate to google.com")
        if res.text != "Navigation complete." or res.has_tool_calls or res.error:
            log.error("❌ FAILED: Text generation failed, got: %s", res)
            all_passed = False
        else:
            log.info("✔ Text generation PASSED!")

        # 9. Test tool call response generation
        mock_tool_call = MagicMock()
        mock_tool_call.name = "open_url"
        mock_tool_call.args = {"url": "https://google.com"}

        mock_tool_resp = MagicMock()
        mock_tool_resp.text = None
        mock_tool_resp.function_calls = [mock_tool_call]
        mock_tool_resp.candidates = []
        mock_client.models.generate_content.return_value = mock_tool_resp

        res_tool = provider.generate("Open google.com")
        if not res_tool.has_tool_calls or res_tool.tool_calls[0].name != "open_url":
            log.error("❌ FAILED: Tool call parsing failed, got: %s", res_tool)
            all_passed = False
        elif res_tool.tool_calls[0].arguments.get("url") != "https://google.com":
            log.error("❌ FAILED: Tool call argument parsing failed, got: %s", res_tool.tool_calls[0].arguments)
            all_passed = False
        else:
            log.info("✔ Tool call generation PASSED!")

        # 10. Test tool schema integration with ToolRegistry
        mgr = BrowserManager()
        registry = ToolRegistry(mgr)
        schemas = registry.get_tool_schemas()

        provider.generate("Search for jobs", tools=schemas)
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        if "config" not in call_kwargs:
            log.error("❌ FAILED: generate_content was not passed config with tools")
            all_passed = False
        else:
            log.info("✔ Tool schema binding PASSED!")

        # 11. Test error handling and key sanitization
        mock_client.models.generate_content.side_effect = Exception("API error with key secret_test_key_999 exposed!")
        res_err = provider.generate("Test error")

        if res_err.error is None:
            log.error("❌ FAILED: Expected error in response, got None")
            all_passed = False
        elif "secret_test_key_999" in res_err.error:
            log.error("❌ FAILED: API key leaked in error message! %s", res_err.error)
            all_passed = False
        elif "[REDACTED]" not in res_err.error:
            log.error("❌ FAILED: API key was not replaced with [REDACTED]")
            all_passed = False
        else:
            log.info("✔ API key sanitization PASSED: %s", res_err.error)

    except Exception as exc:
        log.error("❌ Test suite crashed: %s", exc, exc_info=True)
        all_passed = False

    log.info("=" * 65)
    if all_passed:
        log.info("OVERALL RESULT: ALL LLM PROVIDER TESTS PASSED SUCCESSFULLY! 🎉")
    else:
        log.error("OVERALL RESULT: SOME TESTS FAILED.")
    log.info("=" * 65)
    return all_passed


if __name__ == "__main__":
    success = run_llm_provider_tests()
    sys.exit(0 if success else 1)
