"""LLM 抽象层：多模型统一接口"""
from abc import ABC
from typing import Any, Optional
from openai import OpenAI


class LLMError(Exception):
    """LLM 调用错误"""
    pass


class LLMProvider(ABC):
    """LLM 供应商抽象基类，兼容 OpenAI-compatible API"""

    def __init__(self, api_key: str, model: str, base_url: str, temperature: float = 0.3):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            import httpx
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=httpx.Timeout(300.0, connect=15.0),
                max_retries=1,
            )
        return self._client

    def chat(
        self,
        messages: list[dict[str, str]],
        response_format: Optional[dict[str, str]] = None,
    ) -> str:
        """发送聊天请求，返回响应文本"""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format
        try:
            resp = self.client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(str(e)) from e

    def test_connection(self) -> bool:
        """测试 API 连接是否正常"""
        try:
            self.chat([{"role": "user", "content": "回复 OK"}])
            return True
        except LLMError:
            return False


class DeepSeekProvider(LLMProvider):
    """DeepSeek API"""
    pass


class ClaudeProvider(LLMProvider):
    """Claude API (via Anthropic-compatible endpoint or proxy)"""
    pass


class OpenAIProvider(LLMProvider):
    """OpenAI API"""
    pass


class CustomProvider(LLMProvider):
    """自定义 OpenAI-compatible API"""
    pass


def create_provider(config: dict) -> Optional[LLMProvider]:
    """从配置创建 LLM provider 实例"""
    llm_cfg = config.get("llm", {})
    api_key = llm_cfg.get("api_key", "")
    if not api_key:
        return None
    model = llm_cfg.get("model", "")
    base_url = llm_cfg.get("base_url", "")
    temperature = float(llm_cfg.get("temperature", 0.3))
    provider_name = llm_cfg.get("provider", "custom")

    provider_cls = {
        "deepseek": DeepSeekProvider,
        "claude": ClaudeProvider,
        "openai": OpenAIProvider,
        "custom": CustomProvider,
    }.get(provider_name, CustomProvider)

    return provider_cls(
        api_key=api_key, model=model, base_url=base_url, temperature=temperature
    )
