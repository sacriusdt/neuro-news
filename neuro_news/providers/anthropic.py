from __future__ import annotations

import httpx

from .base import ChatMessage, Provider, ProviderError


class AnthropicProvider(Provider):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def chat(self, messages: list[ChatMessage], model: str, timeout: int) -> str:
        if not self.api_key:
            raise ProviderError("Missing ANTHROPIC_API_KEY")

        system_text = ""
        chat_messages = []
        for message in messages:
            if message.role == "system":
                system_text += message.content
            else:
                chat_messages.append({"role": message.role, "content": message.content})

        payload = {
            "model": model,
            "max_tokens": 800,
            "system": system_text,
            "messages": chat_messages,
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            response = httpx.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        if response.status_code >= 400:
            raise ProviderError(response.text)

        data = response.json()
        return "".join([block["text"] for block in data.get("content", [])])
