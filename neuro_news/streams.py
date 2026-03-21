from __future__ import annotations

import json
from typing import Any

from .db import connect
from .search import SearchFilters, search_articles


def create_stream(db_path: str, name: str, query: str, filters: SearchFilters) -> None:
    payload = {
        "feeds": filters.feeds,
        "categories": filters.categories,
        "subcategories": filters.subcategories,
        "countries": filters.countries,
        "since": filters.since,
        "until": filters.until,
    }
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO streams(name, query, filters_json) VALUES (?, ?, ?)",
        (name, query, json.dumps(payload)),
    )
    conn.commit()
    conn.close()


def list_streams(db_path: str) -> list[dict[str, Any]]:
    conn = connect(db_path)
    rows = conn.execute("SELECT id, name, query, filters_json FROM streams ORDER BY name").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_stream(db_path: str, name: str) -> int:
    conn = connect(db_path)
    cur = conn.execute("DELETE FROM streams WHERE name=?", (name,))
    conn.commit()
    conn.close()
    return cur.rowcount


def run_stream(db_path: str, name: str, limit: int) -> list[dict[str, Any]]:
    conn = connect(db_path)
    row = conn.execute("SELECT query, filters_json FROM streams WHERE name=?", (name,)).fetchone()
    conn.close()
    if not row:
        return []
    payload = json.loads(row[1])
    filters = SearchFilters(
        feeds=payload.get("feeds"),
        categories=payload.get("categories"),
        subcategories=payload.get("subcategories"),
        countries=payload.get("countries"),
        since=payload.get("since"),
        until=payload.get("until"),
    )
    return search_articles(db_path, row[0], filters, limit)
