from __future__ import annotations

from .base import Provider
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .openrouter import OpenRouterProvider


def get_provider(name: str, api_key: str) -> Provider:
    name = name.lower()
    if name == "openai":
        return OpenAIProvider(api_key)
    if name in {"anthropic", "claude"}:
        return AnthropicProvider(api_key)
    if name == "openrouter":
        return OpenRouterProvider(api_key)
    raise ValueError(f"Unknown provider: {name}")
