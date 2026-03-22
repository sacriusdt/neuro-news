from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    category TEXT,
    country TEXT
);

CREATE TABLE IF NOT EXISTS feed_subcategories (
    feed_id INTEGER NOT NULL,
    subcategory TEXT NOT NULL,
    UNIQUE(feed_id, subcategory),
    FOREIGN KEY(feed_id) REFERENCES feeds(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feed_state (
    feed_id INTEGER PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    last_status INTEGER,
    error_count INTEGER NOT NULL DEFAULT 0,
    next_fetch_at TEXT,
    FOREIGN KEY(feed_id) REFERENCES feeds(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    feed_id INTEGER NOT NULL,
    guid TEXT,
    url TEXT,
    title TEXT,
    summary TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    unique_key TEXT NOT NULL UNIQUE,
    FOREIGN KEY(feed_id) REFERENCES feeds(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
    title,
    summary,
    content='articles',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
    INSERT INTO articles_fts(rowid, title, summary)
    VALUES (new.id, new.title, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, summary)
    VALUES('delete', old.id, old.title, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
    INSERT INTO articles_fts(articles_fts, rowid, title, summary)
    VALUES('delete', old.id, old.title, old.summary);
    INSERT INTO articles_fts(rowid, title, summary)
    VALUES (new.id, new.title, new.summary);
END;

CREATE TABLE IF NOT EXISTS streams (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    query TEXT NOT NULL,
    filters_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_feeds_category ON feeds(category);
CREATE INDEX IF NOT EXISTS idx_feeds_country ON feeds(country);
CREATE INDEX IF NOT EXISTS idx_feed_subcategories_subcategory ON feed_subcategories(subcategory);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def add_feed(
    conn: sqlite3.Connection,
    *,
    title: str,
    url: str,
    category: str | None,
    country: str | None,
    subcategories: list[str] | None = None,
) -> int:
    title = title.strip()
    url = url.strip()
    if not title or not url:
        return 0

    conn.execute(
        """
        INSERT INTO feeds (title, url, category, country)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            title=excluded.title,
            category=excluded.category,
            country=excluded.country
        """,
        (title, url, category, country),
    )
    feed_id = conn.execute("SELECT id FROM feeds WHERE url=?", (url,)).fetchone()[0]
    conn.execute("DELETE FROM feed_subcategories WHERE feed_id=?", (feed_id,))
    if subcategories:
        conn.executemany(
            "INSERT OR IGNORE INTO feed_subcategories(feed_id, subcategory) VALUES (?, ?)",
            [(feed_id, sub) for sub in subcategories if sub],
        )
    return 1


def load_feeds(conn: sqlite3.Connection, feeds_path: str) -> int:
    path = Path(feeds_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    inserted = 0

    for feed in data:
        title = feed.get("title", "").strip()
        url = feed.get("url", "").strip()
        category = feed.get("category")
        country = feed.get("country")
        subcategories = feed.get("subcategories", [])

        inserted += add_feed(
            conn,
            title=title,
            url=url,
            category=category,
            country=country,
            subcategories=subcategories,
        )

    conn.commit()
    return inserted


def get_due_feeds(conn: sqlite3.Connection, now_iso: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT f.id, f.title, f.url, fs.etag, fs.last_modified, fs.error_count, fs.next_fetch_at
        FROM feeds f
        LEFT JOIN feed_state fs ON fs.feed_id = f.id
        WHERE fs.next_fetch_at IS NULL OR fs.next_fetch_at <= ?
        ORDER BY f.id
        """,
        (now_iso,),
    ).fetchall()

    return [dict(row) for row in rows]


def update_feed_state(
    conn: sqlite3.Connection,
    feed_id: int,
    *,
    etag: str | None,
    last_modified: str | None,
    last_status: int | None,
    error_count: int,
    next_fetch_at: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO feed_state(feed_id, etag, last_modified, last_status, error_count, next_fetch_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(feed_id) DO UPDATE SET
            etag=excluded.etag,
            last_modified=excluded.last_modified,
            last_status=excluded.last_status,
            error_count=excluded.error_count,
            next_fetch_at=excluded.next_fetch_at
        """,
        (feed_id, etag, last_modified, last_status, error_count, next_fetch_at),
    )


def insert_articles(conn: sqlite3.Connection, articles: Iterable[dict[str, Any]]) -> int:
    rows = list(articles)
    if not rows:
        return 0
    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO articles
        (feed_id, guid, url, title, summary, published_at, fetched_at, unique_key)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["feed_id"],
                row.get("guid"),
                row.get("url"),
                row.get("title"),
                row.get("summary"),
                row.get("published_at"),
                row["fetched_at"],
                row["unique_key"],
            )
            for row in rows
        ],
    )
    return conn.total_changes - before
