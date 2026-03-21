from __future__ import annotations

import httpx

from .base import ChatMessage, Provider, ProviderError


class OpenRouterProvider(Provider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def chat(self, messages: list[ChatMessage], model: str, timeout: int) -> str:
        if not self.api_key:
            raise ProviderError("Missing OPENROUTER_API_KEY")

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": 0.2,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost",
            "X-Title": "neuro-news",
        }

        try:
            response = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        if response.status_code >= 400:
            raise ProviderError(response.text)

        data = response.json()
        return data["choices"][0]["message"]["content"]
