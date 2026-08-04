"""测试 LLM 抽象层"""
import json
import pytest
from unittest.mock import patch, MagicMock
from engine.llm import (
    LLMProvider, DeepSeekProvider, ClaudeProvider,
    OpenAIProvider, CustomProvider, create_provider, LLMError
)


SAMPLE_CONFIG = {
    "llm": {
        "provider": "deepseek",
        "api_key": "test-key",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "temperature": 0.3,
    }
}


class TestCreateProvider:
    def test_creates_deepseek(self):
        provider = create_provider(SAMPLE_CONFIG)
        assert isinstance(provider, DeepSeekProvider)

    def test_creates_claude(self):
        config = {"llm": {**SAMPLE_CONFIG["llm"], "provider": "claude"}}
        provider = create_provider(config)
        assert isinstance(provider, ClaudeProvider)

    def test_creates_openai(self):
        config = {"llm": {**SAMPLE_CONFIG["llm"], "provider": "openai"}}
        provider = create_provider(config)
        assert isinstance(provider, OpenAIProvider)

    def test_creates_custom(self):
        config = {"llm": {**SAMPLE_CONFIG["llm"], "provider": "custom"}}
        provider = create_provider(config)
        assert isinstance(provider, CustomProvider)

    def test_unknown_provider_defaults_to_custom(self):
        config = {"llm": {**SAMPLE_CONFIG["llm"], "provider": "unknown_xyz"}}
        provider = create_provider(config)
        assert isinstance(provider, CustomProvider)

    def test_missing_api_key_returns_none(self):
        config = {"llm": {**SAMPLE_CONFIG["llm"], "api_key": ""}}
        provider = create_provider(config)
        assert provider is None


class TestProviderInterface:
    def test_deepseek_sets_correct_base_url(self):
        provider = DeepSeekProvider(
            api_key="k", model="m", base_url="https://api.deepseek.com/v1", temperature=0.3
        )
        assert provider.base_url == "https://api.deepseek.com/v1"

    def test_custom_provider_accepts_any_url(self):
        provider = CustomProvider(
            api_key="k", model="m", base_url="https://custom.api.com/v1", temperature=0.5
        )
        assert provider.base_url == "https://custom.api.com/v1"

    @patch("engine.llm.OpenAI")
    def test_chat_calls_openai_sdk(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"result": "ok"}'))]
        )
        mock_openai_cls.return_value = mock_client

        provider = DeepSeekProvider(
            api_key="k", model="m", base_url="https://test.com", temperature=0.3
        )
        result = provider.chat([{"role": "user", "content": "hi"}])
        assert '"result": "ok"' in result
        mock_client.chat.completions.create.assert_called_once()

    @patch("engine.llm.OpenAI")
    def test_chat_with_json_response_format(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"key": "value"}'))]
        )
        mock_openai_cls.return_value = mock_client

        provider = DeepSeekProvider(
            api_key="k", model="m", base_url="https://test.com", temperature=0.3
        )
        result = provider.chat(
            [{"role": "user", "content": "hi"}],
            response_format={"type": "json_object"}
        )
        assert "key" in result

    @patch("engine.llm.OpenAI")
    def test_chat_handles_api_error(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        mock_openai_cls.return_value = mock_client

        provider = DeepSeekProvider(
            api_key="k", model="m", base_url="https://test.com", temperature=0.3
        )
        with pytest.raises(LLMError, match="API error"):
            provider.chat([{"role": "user", "content": "hi"}])

    @patch("engine.llm.OpenAI")
    def test_test_connection_success(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="pong"))]
        )
        mock_openai_cls.return_value = mock_client

        provider = DeepSeekProvider(
            api_key="k", model="m", base_url="https://test.com", temperature=0.3
        )
        assert provider.test_connection() is True

    @patch("engine.llm.OpenAI")
    def test_test_connection_failure(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Connection refused")
        mock_openai_cls.return_value = mock_client

        provider = DeepSeekProvider(
            api_key="k", model="m", base_url="https://test.com", temperature=0.3
        )
        assert provider.test_connection() is False
