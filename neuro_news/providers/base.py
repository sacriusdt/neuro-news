from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class ChatMessage:
    role: str
    content: str


class ProviderError(RuntimeError):
    pass


class Provider:
    def chat(self, messages: Iterable[ChatMessage], model: str, timeout: int) -> str:
        raise NotImplementedError
