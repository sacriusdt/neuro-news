from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx
from dateutil import parser as date_parser

from .db import connect, get_due_feeds, insert_articles, update_feed_state


@dataclass
class FetchResult:
    feed_id: int
    status: int | None
    etag: str | None
    last_modified: str | None
    error: str | None
    entries: list[dict[str, Any]]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def canonicalize_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    raw_url = raw_url.strip()
    if not raw_url:
        return None
    parts = urlsplit(raw_url)
    scheme = parts.scheme.lower() or "http"
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, "", ""))


def parse_entry_date(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        struct_time = entry.get(key)
        if struct_time:
            timestamp = _mktime_tz_safe(struct_time)
            if timestamp is not None:
                return datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
    for key in ("published", "updated"):
        text = entry.get(key)
        if text:
            try:
                return date_parser.parse(text).astimezone(timezone.utc)
            except Exception:
                return None
    return None


def _mktime_tz_safe(struct_time: Any) -> int | None:
    if hasattr(feedparser, "mktime_tz"):
        return feedparser.mktime_tz(struct_time)
    try:
        from email.utils import mktime_tz as email_mktime_tz

        return email_mktime_tz(struct_time)
    except Exception:
        try:
            import calendar

            return calendar.timegm(struct_time)
        except Exception:
            return None


def build_unique_key(guid: str | None, url: str | None, title: str | None, published_at: str | None) -> str:
    base = guid or url or f"{title or ''}|{published_at or ''}"
    return hashlib.sha256(base.encode("utf-8", "ignore")).hexdigest()


def parse_feed_entries(feed_id: int, raw_content: bytes, fetched_at: str) -> list[dict[str, Any]]:
    parsed = feedparser.parse(raw_content)
    entries: list[dict[str, Any]] = []

    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        link = canonicalize_url(entry.get("link"))
        guid = entry.get("id") or entry.get("guid")
        published_dt = parse_entry_date(entry)
        published_at = to_iso(published_dt)
        unique_key = build_unique_key(guid, link, title, published_at)

        entries.append(
            {
                "feed_id": feed_id,
                "guid": guid,
                "url": link,
                "title": title,
                "summary": summary,
                "published_at": published_at,
                "fetched_at": fetched_at,
                "unique_key": unique_key,
            }
        )

    return entries


async def fetch_feed(client: httpx.AsyncClient, feed: dict[str, Any], timeout: int) -> FetchResult:
    headers = {}
    if feed.get("etag"):
        headers["If-None-Match"] = feed["etag"]
    if feed.get("last_modified"):
        headers["If-Modified-Since"] = feed["last_modified"]

    try:
        response = await client.get(feed["url"], headers=headers, timeout=timeout)
    except Exception as exc:
        return FetchResult(feed["id"], None, feed.get("etag"), feed.get("last_modified"), str(exc), [])

    if response.status_code == 304:
        return FetchResult(feed["id"], 304, feed.get("etag"), feed.get("last_modified"), None, [])

    if response.status_code != 200:
        return FetchResult(feed["id"], response.status_code, feed.get("etag"), feed.get("last_modified"), "http_error", [])

    fetched_at = to_iso(utc_now()) or ""
    entries = parse_feed_entries(feed["id"], response.content, fetched_at)
    etag = response.headers.get("ETag")
    last_modified = response.headers.get("Last-Modified")
    return FetchResult(feed["id"], 200, etag, last_modified, None, entries)


async def fetch_all(db_path: str, poll_interval_minutes: int, timeout: int, max_concurrency: int) -> dict[str, Any]:
    now_iso = to_iso(utc_now()) or ""
    conn = connect(db_path)
    due_feeds = get_due_feeds(conn, now_iso)
    if not due_feeds:
        conn.close()
        return {"fetched": 0, "inserted": 0, "errors": 0}

    semaphore = asyncio.Semaphore(max_concurrency)

    async def run(feed: dict[str, Any]) -> FetchResult:
        async with semaphore:
            return await fetch_feed(client, feed, timeout)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [run(feed) for feed in due_feeds]
        results = await asyncio.gather(*tasks)

    inserted_total = 0
    errors = 0
    for result in results:
        if result.error or (result.status not in (200, 304)):
            errors += 1

        error_count = 0
        next_fetch = utc_now() + timedelta(minutes=poll_interval_minutes)

        if result.error or (result.status not in (200, 304)):
            error_count = (
                conn.execute("SELECT error_count FROM feed_state WHERE feed_id=?", (result.feed_id,))
                .fetchone()
            )
            current_errors = error_count[0] if error_count else 0
            current_errors += 1
            delay_minutes = min(poll_interval_minutes * (2**current_errors), 360)
            next_fetch = utc_now() + timedelta(minutes=delay_minutes)
            error_count = current_errors

        update_feed_state(
            conn,
            result.feed_id,
            etag=result.etag,
            last_modified=result.last_modified,
            last_status=result.status,
            error_count=error_count,
            next_fetch_at=to_iso(next_fetch),
        )

        if result.entries:
            inserted_total += insert_articles(conn, result.entries)

    conn.commit()
    conn.close()

    return {"fetched": len(results), "inserted": inserted_total, "errors": errors}
