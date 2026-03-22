from __future__ import annotations

import json
from typing import Any

from .config import AppConfig, get_model_for_provider
from .db import connect
from .providers.base import ChatMessage, ProviderError
from .providers.registry import get_provider
from .search import SearchFilters, search_articles


EXTRACT_SYSTEM = (
    "You extract search parameters from a user request about news articles. "
    "Return JSON only with keys: query, filters, limit, sort. "
    "filters can include: feeds (list), categories (list), subcategories (list), countries (list), "
    "since (string), until (string). "
    "Always use arrays for feeds/categories/subcategories/countries, even for a single value. "
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
    if not isinstance(filters, dict):
        filters = {}
    return SearchFilters(
        feeds=_ensure_list(filters.get("feeds")),
        categories=_ensure_list(filters.get("categories")),
        subcategories=_ensure_list(filters.get("subcategories")),
        countries=_ensure_list(filters.get("countries")),
        since=filters.get("since"),
        until=filters.get("until"),
    )


def extract_request(message: str, config: AppConfig, provider_name: str | None, model: str | None) -> dict[str, Any]:
    provider = provider_name or config.provider
    model_name = model or get_model_for_provider(provider, config)
    api_key = _select_api_key(config, provider)

    client = get_provider(provider, api_key)
    system_text = EXTRACT_SYSTEM
    context = _build_extract_context(config.db_path)
    if context:
        system_text = f"{EXTRACT_SYSTEM}\n\nKnown values:\n{context}"
    messages = [
        ChatMessage(role="system", content=system_text),
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
    payload["query"] = _coerce_query(payload.get("query"), message)
    payload["limit"] = _coerce_limit(payload.get("limit"), config.max_results)
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

    articles = _search_with_fallback(config.db_path, query, filters, int(limit))
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


def _ensure_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value]
    return [str(value)]


def _coerce_query(value: Any, fallback: str) -> str:
    if isinstance(value, list):
        parts = [str(item) for item in value if str(item).strip()]
        return " ".join(parts) if parts else fallback
    if isinstance(value, str):
        text = value.strip()
        return text or fallback
    return fallback


def _coerce_limit(value: Any, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except Exception:
        return default


def _build_extract_context(db_path: str) -> str:
    try:
        conn = connect(db_path)
    except Exception:
        return ""

    categories = [row[0] for row in conn.execute(
        "SELECT DISTINCT category FROM feeds WHERE category IS NOT NULL ORDER BY category LIMIT 30"
    ).fetchall()]
    subcategories = [row[0] for row in conn.execute(
        "SELECT DISTINCT subcategory FROM feed_subcategories ORDER BY subcategory LIMIT 40"
    ).fetchall()]
    countries = [row[0] for row in conn.execute(
        "SELECT DISTINCT country FROM feeds WHERE country IS NOT NULL ORDER BY country LIMIT 30"
    ).fetchall()]
    feeds = [row[0] for row in conn.execute(
        "SELECT title FROM feeds ORDER BY title LIMIT 30"
    ).fetchall()]
    conn.close()

    lines = []
    if categories:
        lines.append("Categories: " + ", ".join(categories))
    if subcategories:
        lines.append("Subcategories: " + ", ".join(subcategories))
    if countries:
        lines.append("Countries: " + ", ".join(countries))
    if feeds:
        lines.append("Feeds: " + ", ".join(feeds))
    return "\n".join(lines)


def _filters_signature(filters: SearchFilters) -> tuple:
    return (
        tuple(sorted(filters.feeds)),
        tuple(sorted(filters.categories)),
        tuple(sorted(filters.subcategories)),
        tuple(sorted(filters.countries)),
        filters.since or "",
        filters.until or "",
    )


def _clone_filters(filters: SearchFilters, **overrides: Any) -> SearchFilters:
    return SearchFilters(
        feeds=overrides.get("feeds", list(filters.feeds)),
        categories=overrides.get("categories", list(filters.categories)),
        subcategories=overrides.get("subcategories", list(filters.subcategories)),
        countries=overrides.get("countries", list(filters.countries)),
        since=overrides.get("since", filters.since),
        until=overrides.get("until", filters.until),
    )


def _search_with_fallback(
    db_path: str,
    query: str,
    filters: SearchFilters,
    limit: int,
) -> list[dict[str, Any]]:
    attempts = [_clone_filters(filters)]
    if filters.countries:
        attempts.append(_clone_filters(filters, countries=[]))
    if filters.subcategories:
        attempts.append(_clone_filters(filters, subcategories=[]))
    if filters.categories:
        attempts.append(_clone_filters(filters, categories=[]))
    if filters.feeds:
        attempts.append(_clone_filters(filters, feeds=[]))
    attempts.append(SearchFilters())

    seen = set()
    for attempt in attempts:
        signature = _filters_signature(attempt)
        if signature in seen:
            continue
        seen.add(signature)
        results = search_articles(db_path, query, attempt, limit, fts_mode="or")
        if results:
            return results

    return []
