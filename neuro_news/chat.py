from __future__ import annotations

import json
from typing import Any

from .config import AppConfig, get_model_for_provider
from .providers.base import ChatMessage, ProviderError
from .providers.registry import get_provider
from .search import SearchFilters, search_articles


EXTRACT_SYSTEM = (
    "You extract search parameters from a user request about news articles. "
    "Return JSON only with keys: query, filters, limit, sort. "
    "filters can include: feeds (list), categories (list), subcategories (list), countries (list), "
    "since (string), until (string). "
    "sort can be 'published' or 'fetched'. "
    "If unsure, keep fields empty or null."
)

ANSWER_SYSTEM = (
    "You answer questions about news articles. Use the provided list only. "
    "Cite sources using [n] where n matches the list item number. "
    "If the list is empty, say you could not find matching articles."
)


def _extract_json(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def _build_filters(payload: dict[str, Any]) -> SearchFilters:
    filters = payload.get("filters") or {}
    return SearchFilters(
        feeds=filters.get("feeds") or [],
        categories=filters.get("categories") or [],
        subcategories=filters.get("subcategories") or [],
        countries=filters.get("countries") or [],
        since=filters.get("since"),
        until=filters.get("until"),
    )


def extract_request(message: str, config: AppConfig, provider_name: str | None, model: str | None) -> dict[str, Any]:
    provider = provider_name or config.provider
    model_name = model or get_model_for_provider(provider, config)
    api_key = _select_api_key(config, provider)

    client = get_provider(provider, api_key)
    messages = [
        ChatMessage(role="system", content=EXTRACT_SYSTEM),
        ChatMessage(role="user", content=message),
    ]

    try:
        text = client.chat(messages, model_name, config.timeout_seconds)
    except ProviderError:
        return {"query": message, "filters": {}, "limit": config.max_results, "sort": "published"}

    payload = _extract_json(text) or {}
    payload.setdefault("query", message)
    payload.setdefault("filters", {})
    payload.setdefault("limit", config.max_results)
    payload.setdefault("sort", "published")
    return payload


def answer_with_citations(
    message: str,
    articles: list[dict[str, Any]],
    config: AppConfig,
    provider_name: str | None,
    model: str | None,
) -> str:
    provider = provider_name or config.provider
    model_name = model or get_model_for_provider(provider, config)
    api_key = _select_api_key(config, provider)

    client = get_provider(provider, api_key)

    lines = []
    for index, article in enumerate(articles, start=1):
        lines.append(
            f"{index}. Title: {article.get('title') or 'Untitled'} | "
            f"URL: {article.get('url') or 'N/A'} | "
            f"Feed: {article.get('feed_title') or 'Unknown'} | "
            f"Date: {article.get('published_at') or article.get('fetched_at') or 'N/A'}"
        )

    context = "\n".join(lines)
    prompt = (
        f"User question: {message}\n\n"
        f"Articles:\n{context}\n\n"
        "Answer in the same language as the user. Use citations like [1]."
    )

    messages = [
        ChatMessage(role="system", content=ANSWER_SYSTEM),
        ChatMessage(role="user", content=prompt),
    ]

    return client.chat(messages, model_name, config.timeout_seconds)


def run_chat(
    message: str,
    config: AppConfig,
    provider_name: str | None,
    model: str | None,
) -> dict[str, Any]:
    payload = extract_request(message, config, provider_name, model)
    query = payload.get("query") or ""
    filters = _build_filters(payload)
    limit = payload.get("limit") or config.max_results

    articles = search_articles(config.db_path, query, filters, int(limit))
    answer = answer_with_citations(message, articles, config, provider_name, model)

    return {"answer": answer, "articles": articles}


def _select_api_key(config: AppConfig, provider: str) -> str:
    provider = provider.lower()
    if provider == "openai":
        return config.openai_api_key or ""
    if provider in {"anthropic", "claude"}:
        return config.anthropic_api_key or ""
    if provider == "openrouter":
        return config.openrouter_api_key or ""
    return ""
