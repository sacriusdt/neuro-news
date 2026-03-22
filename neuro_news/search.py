from __future__ import annotations

import re
import unicodedata
from typing import Any

from dateutil import parser as date_parser

from .db import connect


class SearchFilters:
    def __init__(
        self,
        feeds: list[str] | None = None,
        categories: list[str] | None = None,
        subcategories: list[str] | None = None,
        countries: list[str] | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> None:
        self.feeds = feeds or []
        self.categories = categories or []
        self.subcategories = subcategories or []
        self.countries = countries or []
        self.since = since
        self.until = until


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        return dt.isoformat()
    except Exception:
        return None


def resolve_feed_ids(conn, feed_values: list[str]) -> list[int]:
    if not feed_values:
        return []
    ids: list[int] = []
    for value in feed_values:
        value = value.strip().lower()
        if not value:
            continue
        rows = conn.execute(
            "SELECT id FROM feeds WHERE lower(title) LIKE ? OR lower(url) LIKE ?",
            (f"%{value}%", f"%{value}%"),
        ).fetchall()
        ids.extend([row[0] for row in rows])
    return sorted(set(ids))


def _strip_accents(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def normalize_country(value: str) -> str:
    raw = _strip_accents(value.strip().lower())
    raw = raw.replace(".", " ").replace("-", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    aliases = {
        "etats unis": "United States",
        "etat unis": "United States",
        "etats-unis": "United States",
        "usa": "United States",
        "us": "United States",
        "united states of america": "United States",
        "royaume uni": "United Kingdom",
        "royaume-uni": "United Kingdom",
        "uk": "United Kingdom",
        "angleterre": "United Kingdom",
    }
    return aliases.get(raw, value.strip())


STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "for",
    "with",
    "about",
    "on",
    "in",
    "to",
    "of",
    "de",
    "des",
    "du",
    "la",
    "le",
    "les",
    "un",
    "une",
    "et",
    "ou",
    "mais",
    "sur",
    "dans",
    "pour",
    "avec",
    "au",
    "aux",
    "par",
    "plus",
    "latest",
    "recent",
    "dernier",
    "derniers",
    "recentes",
}


def tokenize_query(query: str) -> list[str]:
    cleaned = _strip_accents(query.lower())
    cleaned = re.sub(r"[^\w\s]", " ", cleaned, flags=re.UNICODE)
    tokens = [token for token in re.split(r"\s+", cleaned.strip()) if token]
    keywords = []
    for token in tokens:
        if len(token) < 3:
            continue
        if token in STOPWORDS:
            continue
        keywords.append(token)
    return keywords


def build_fts_query(query: str, mode: str = "and") -> str:
    raw_tokens = tokenize_query(query)
    if not raw_tokens:
        raw_tokens = [token for token in re.split(r"\s+", query.strip()) if token]
    if not raw_tokens:
        return ""
    safe = [token.replace('"', "") for token in raw_tokens]
    quoted = [f'"{token}"' for token in safe if token]
    if not quoted:
        return ""
    joiner = " OR " if mode.lower() == "or" else " "
    return joiner.join(quoted)


def search_articles(
    db_path: str,
    query: str | None,
    filters: SearchFilters,
    limit: int,
    fts_mode: str = "and",
) -> list[dict[str, Any]]:
    conn = connect(db_path)

    sql = (
        "SELECT a.id, a.title, a.url, a.summary, a.published_at, a.fetched_at, "
        "f.title as feed_title, f.category, f.country "
        "FROM articles a "
        "JOIN feeds f ON f.id = a.feed_id "
    )
    where = []
    params: list[Any] = []

    if query:
        fts_query = build_fts_query(query, fts_mode)
        if fts_query:
            sql = (
                "SELECT a.id, a.title, a.url, a.summary, a.published_at, a.fetched_at, "
                "f.title as feed_title, f.category, f.country "
                "FROM articles_fts fts "
                "JOIN articles a ON a.id = fts.rowid "
                "JOIN feeds f ON f.id = a.feed_id "
            )
            where.append("articles_fts MATCH ?")
            params.append(fts_query)

    feed_ids = resolve_feed_ids(conn, filters.feeds)
    if feed_ids:
        placeholders = ",".join("?" for _ in feed_ids)
        where.append(f"a.feed_id IN ({placeholders})")
        params.extend(feed_ids)

    if filters.categories:
        placeholders = ",".join("?" for _ in filters.categories)
        where.append(f"f.category IN ({placeholders})")
        params.extend(filters.categories)

    if filters.countries:
        normalized = [normalize_country(country) for country in filters.countries]
        placeholders = ",".join("?" for _ in normalized)
        where.append(f"lower(f.country) IN ({placeholders})")
        params.extend([value.lower() for value in normalized])

    if filters.subcategories:
        placeholders = ",".join("?" for _ in filters.subcategories)
        where.append(
            "EXISTS (SELECT 1 FROM feed_subcategories fs WHERE fs.feed_id = f.id "
            f"AND fs.subcategory IN ({placeholders}))"
        )
        params.extend(filters.subcategories)

    since = parse_date(filters.since)
    until = parse_date(filters.until)
    if since:
        where.append("COALESCE(a.published_at, a.fetched_at) >= ?")
        params.append(since)
    if until:
        where.append("COALESCE(a.published_at, a.fetched_at) <= ?")
        params.append(until)

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY COALESCE(a.published_at, a.fetched_at) DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]
