from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .chat import run_chat
from .config import ConfigStore
from .db import connect, init_db, load_feeds
from .ingest import fetch_all
from .providers.base import ProviderError
from .search import SearchFilters, search_articles
from .streams import create_stream, delete_stream, list_streams, run_stream
from .ui import (
    get_random_tip,
    print_banner,
    print_error,
    print_info,
    print_result_count,
    print_success,
    print_tip,
    print_warning,
    show_commands_menu,
    spinner,
)

app = typer.Typer(
    help="Neuro News — AI-powered news terminal.",
    no_args_is_help=False,
    pretty_exceptions_enable=False,
)
feeds_app = typer.Typer(help="Manage RSS feed sources.")
streams_app = typer.Typer(help="Manage saved search streams.")
app.add_typer(feeds_app, name="feeds")
app.add_typer(streams_app, name="streams")
console = Console()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_config():
    store = ConfigStore()
    return store, store.load()


def _ensure_db(db_path: str) -> None:
    if not Path(db_path).exists():
        print_error("Database not found. Run [bold cyan]neuro-news init[/] first.")
        raise typer.Exit(1)


def _format_date(raw: str) -> str:
    """Trim datetime strings to a readable date."""
    if not raw:
        return "—"
    return raw[:10] if len(raw) > 10 else raw


# ---------------------------------------------------------------------------
# Commands menu — invoked with no args, "commands", or "/" (PowerShell/CMD)
# ---------------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        show_commands_menu()


@app.command(name="commands", hidden=False)
def commands_menu() -> None:
    """Show all available commands (alias: just run neuro-news with no arguments)."""
    show_commands_menu()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command()
def init(
    feeds_path: str = typer.Option("feeds.json", help="Path to feeds.json"),
) -> None:
    """Set up the database and load feeds from a JSON file."""
    store, config = _load_config()
    Path(config.db_path).parent.mkdir(parents=True, exist_ok=True)

    with spinner("Initialising database…"):
        conn = connect(config.db_path)
        init_db(conn)
        count = load_feeds(conn, feeds_path)
        conn.close()
        store.save(config)

    console.print(
        Panel(
            f"[bold green]✓[/] Loaded [bold]{count}[/] feeds.\n"
            f"[dim]Database:[/] {config.db_path}",
            title="[bold cyan]Neuro News — Ready[/]",
            border_style="cyan",
            expand=False,
        )
    )
    print_tip()


@app.command()
def fetch() -> None:
    """Fetch the latest articles from all feeds."""
    store, config = _load_config()
    _ensure_db(config.db_path)

    with spinner("Fetching feeds…", style="bold blue"):
        result = asyncio.run(
            fetch_all(
                config.db_path,
                config.poll_interval_minutes,
                config.timeout_seconds,
                config.max_concurrency,
            )
        )

    fetched = result["fetched"]
    inserted = result["inserted"]
    errors = result["errors"]

    status_lines = [
        f"[bold]{fetched}[/] feeds polled",
        f"[bold green]+{inserted}[/] new articles",
    ]
    if errors:
        status_lines.append(f"[bold red]{errors}[/] error(s)")

    console.print(
        Panel(
            "  ·  ".join(status_lines),
            title="[bold blue]Fetch complete[/]",
            border_style="blue",
            expand=False,
        )
    )

    # Show a tip occasionally (roughly 1 in 3 fetches)
    import random
    if random.random() < 0.35:
        print_tip()


@app.command()
def watch(
    interval: Optional[int] = typer.Option(None, help="Polling interval in minutes (default from config)"),
) -> None:
    """Continuously fetch new articles on a set interval. Press Ctrl+C to stop."""
    store, config = _load_config()
    _ensure_db(config.db_path)
    poll_interval = interval or config.poll_interval_minutes

    console.print(
        Panel(
            f"Polling every [bold]{poll_interval}[/] minute(s).  Press [bold]Ctrl+C[/] to stop.",
            title="[bold blue]Watch mode[/]",
            border_style="blue",
            expand=False,
        )
    )

    cycle = 0
    while True:
        cycle += 1
        with spinner(f"Cycle {cycle} — fetching…", style="bold blue"):
            result = asyncio.run(
                fetch_all(
                    config.db_path,
                    poll_interval,
                    config.timeout_seconds,
                    config.max_concurrency,
                )
            )

        fetched = result["fetched"]
        inserted = result["inserted"]
        errors = result["errors"]
        err_str = f"  [bold red]{errors} error(s)[/]" if errors else ""

        print_success(
            f"[dim]#{cycle}[/]  {fetched} feeds  ·  [green]+{inserted}[/] articles{err_str}"
        )
        time.sleep(poll_interval * 60)


@feeds_app.command("list")
def feeds_list() -> None:
    """List all configured RSS feed sources."""
    store, config = _load_config()
    _ensure_db(config.db_path)
    conn = connect(config.db_path)
    rows = conn.execute(
        """
        SELECT f.id, f.title, f.url, f.category, f.country,
               group_concat(fs.subcategory, ', ') as subcategories
        FROM feeds f
        LEFT JOIN feed_subcategories fs ON fs.feed_id = f.id
        GROUP BY f.id
        ORDER BY f.title
        """
    ).fetchall()
    conn.close()

    table = Table(
        title=f"[bold]RSS Feeds[/] [dim]({len(rows)} total)[/]",
        header_style="bold magenta",
        border_style="dim",
        show_lines=False,
        expand=True,
    )
    table.add_column("#", style="dim", justify="right", no_wrap=True, width=4)
    table.add_column("Title", style="bold white", min_width=20)
    table.add_column("Category", style="cyan")
    table.add_column("Country", style="green")
    table.add_column("Subcategories", style="dim")
    table.add_column("URL", style="dim blue")

    for row in rows:
        table.add_row(
            str(row[0]),
            row[1],
            row[3] or "—",
            row[4] or "—",
            row[5] or "—",
            row[2],
        )

    console.print(table)


@app.command()
def search(
    query: Optional[str] = typer.Argument(None, help="Keywords to search for"),
    feed: list[str] = typer.Option([], "--feed", help="Filter by feed title or URL"),
    category: list[str] = typer.Option([], "--category", help="Filter by category"),
    subcategory: list[str] = typer.Option([], "--subcategory", help="Filter by subcategory"),
    country: list[str] = typer.Option([], "--country", help="Filter by country"),
    since: Optional[str] = typer.Option(None, help="Only articles after this date (YYYY-MM-DD)"),
    until: Optional[str] = typer.Option(None, help="Only articles before this date (YYYY-MM-DD)"),
    limit: Optional[int] = typer.Option(None, help="Maximum number of results"),
) -> None:
    """Search articles by keyword with optional filters."""
    store, config = _load_config()
    _ensure_db(config.db_path)

    filters = SearchFilters(
        feeds=feed,
        categories=category,
        subcategories=subcategory,
        countries=country,
        since=since,
        until=until,
    )

    with spinner("Searching…"):
        results = search_articles(
            config.db_path,
            query,
            filters,
            limit or config.max_results,
        )

    # Build title from active filters
    parts: list[str] = []
    if query:
        parts.append(f'"{query}"')
    if feed:
        parts.append(f"feed:{', '.join(feed)}")
    if category:
        parts.append(f"category:{', '.join(category)}")
    if country:
        parts.append(f"country:{', '.join(country)}")
    title_str = "  ·  ".join(parts) if parts else "All articles"

    table = Table(
        title=f"[bold]Search:[/] {title_str}",
        header_style="bold magenta",
        border_style="dim",
        show_lines=False,
        expand=True,
    )
    table.add_column("Date", style="dim", no_wrap=True, width=10)
    table.add_column("Feed", style="cyan", no_wrap=True, min_width=14)
    table.add_column("Title", style="white", ratio=3)
    table.add_column("URL", style="dim blue", ratio=2)

    for row in results:
        raw_date = row.get("published_at") or row.get("fetched_at") or ""
        table.add_row(
            _format_date(raw_date),
            row.get("feed_title") or "—",
            row.get("title") or "—",
            row.get("url") or "—",
        )

    console.print(table)
    print_result_count(len(results), "article")


@app.command()
def stats() -> None:
    """Show a snapshot of the database: feeds, articles, and streams."""
    store, config = _load_config()
    _ensure_db(config.db_path)
    conn = connect(config.db_path)
    feed_count = conn.execute("SELECT COUNT(*) FROM feeds").fetchone()[0]
    article_count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    stream_count = conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0]

    # Most recent article date
    latest = conn.execute(
        "SELECT MAX(published_at) FROM articles"
    ).fetchone()[0]

    # Top 3 categories by article count
    top_cats = conn.execute(
        """
        SELECT f.category, COUNT(*) as cnt
        FROM articles a
        JOIN feeds f ON f.id = a.feed_id
        WHERE f.category IS NOT NULL
        GROUP BY f.category
        ORDER BY cnt DESC
        LIMIT 3
        """
    ).fetchall()
    conn.close()

    lines = [
        f"[bold cyan]{feed_count:,}[/]     RSS feeds",
        f"[bold green]{article_count:,}[/]  articles indexed",
        f"[bold yellow]{stream_count:,}[/]     saved streams",
    ]
    if latest:
        lines.append(f"\n[dim]Latest article:[/] {_format_date(latest)}")
    if top_cats:
        cats_str = "  ·  ".join(
            f"[cyan]{c[0]}[/] [dim]({c[1]})[/]" for c in top_cats
        )
        lines.append(f"[dim]Top categories:[/] {cats_str}")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold]Neuro News — Stats[/]",
            border_style="cyan",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# Streams
# ---------------------------------------------------------------------------

@streams_app.command("list")
def streams_list() -> None:
    """List all saved search streams."""
    store, config = _load_config()
    _ensure_db(config.db_path)
    rows = list_streams(config.db_path)

    if not rows:
        print_info("No streams saved yet. Create one with [bold cyan]streams create <name>[/]")
        return

    table = Table(
        title=f"[bold]Saved Streams[/] [dim]({len(rows)} total)[/]",
        header_style="bold magenta",
        border_style="dim",
        expand=True,
    )
    table.add_column("Name", style="bold cyan", no_wrap=True)
    table.add_column("Query", style="white")
    table.add_column("Filters", style="dim")

    for row in rows:
        table.add_row(row["name"], row["query"] or "—", row["filters_json"])

    console.print(table)


@streams_app.command("create")
def streams_create(
    name: str = typer.Argument(..., help="A unique name for this stream"),
    query: Optional[str] = typer.Option(None, help="Search keywords"),
    feed: list[str] = typer.Option([], "--feed", help="Filter by feed title or URL"),
    category: list[str] = typer.Option([], "--category", help="Filter by category"),
    subcategory: list[str] = typer.Option([], "--subcategory", help="Filter by subcategory"),
    country: list[str] = typer.Option([], "--country", help="Filter by country"),
    since: Optional[str] = typer.Option(None, help="Since date (YYYY-MM-DD)"),
    until: Optional[str] = typer.Option(None, help="Until date (YYYY-MM-DD)"),
) -> None:
    """Create a new saved search stream."""
    store, config = _load_config()
    _ensure_db(config.db_path)

    if not query:
        print_error("A search [bold]--query[/] is required to create a stream.")
        raise typer.Exit(1)

    filters = SearchFilters(
        feeds=feed,
        categories=category,
        subcategories=subcategory,
        countries=country,
        since=since,
        until=until,
    )
    create_stream(config.db_path, name, query, filters)
    print_success(
        f"Stream [bold cyan]{name}[/] created.  Run it with [bold]streams run {name}[/]"
    )


@streams_app.command("delete")
def streams_delete(name: str = typer.Argument(..., help="Name of the stream to delete")) -> None:
    """Delete a saved search stream."""
    store, config = _load_config()
    _ensure_db(config.db_path)
    deleted = delete_stream(config.db_path, name)
    if deleted:
        print_success(f"Stream [bold cyan]{name}[/] deleted.")
    else:
        print_warning(f"Stream [bold cyan]{name}[/] not found.")


@streams_app.command("run")
def streams_run(
    name: str = typer.Argument(..., help="Name of the stream to run"),
    limit: Optional[int] = typer.Option(None, help="Maximum number of results"),
) -> None:
    """Run a saved search stream and display the results."""
    store, config = _load_config()
    _ensure_db(config.db_path)

    with spinner(f"Running stream [bold cyan]{name}[/]…"):
        results = run_stream(config.db_path, name, limit or config.max_results)

    table = Table(
        title=f"[bold]Stream:[/] {name}",
        header_style="bold magenta",
        border_style="dim",
        show_lines=False,
        expand=True,
    )
    table.add_column("Date", style="dim", no_wrap=True, width=10)
    table.add_column("Feed", style="cyan", no_wrap=True, min_width=14)
    table.add_column("Title", style="white", ratio=3)
    table.add_column("URL", style="dim blue", ratio=2)

    for row in results:
        raw_date = row.get("published_at") or row.get("fetched_at") or ""
        table.add_row(
            _format_date(raw_date),
            row.get("feed_title") or "—",
            row.get("title") or "—",
            row.get("url") or "—",
        )

    console.print(table)
    print_result_count(len(results), "article")


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.command()
def chat(
    message: str = typer.Argument(..., help="Your question in natural language"),
    provider: Optional[str] = typer.Option(None, help="AI provider: openai, anthropic, openrouter"),
    model: Optional[str] = typer.Option(None, help="Override the default model"),
    limit: Optional[int] = typer.Option(None, help="Maximum number of source articles"),
) -> None:
    """Ask a natural-language question answered from your news database."""
    store, config = _load_config()
    _ensure_db(config.db_path)

    if limit:
        config.max_results = limit

    try:
        with spinner("Thinking…", style="bold magenta"):
            result = run_chat(message, config, provider, model)
    except ProviderError as exc:
        print_error(str(exc))
        raise typer.Exit(1) from exc

    # Display the answer in a styled panel
    console.print()
    console.print(
        Panel(
            result["answer"],
            title="[bold magenta]Answer[/]",
            border_style="magenta",
            padding=(1, 2),
        )
    )

    # Sources
    if result["articles"]:
        sources_table = Table(
            title="[bold]Sources[/]",
            header_style="bold dim",
            border_style="dim",
            show_lines=False,
            expand=True,
        )
        sources_table.add_column("#", style="dim", width=3, justify="right")
        sources_table.add_column("Title", style="white", ratio=2)
        sources_table.add_column("Feed", style="cyan", no_wrap=True)
        sources_table.add_column("Date", style="dim", no_wrap=True, width=10)
        sources_table.add_column("URL", style="dim blue", ratio=2)

        for index, article in enumerate(result["articles"], start=1):
            raw_date = article.get("published_at") or article.get("fetched_at") or ""
            sources_table.add_row(
                str(index),
                article.get("title") or "Untitled",
                article.get("feed_title") or "—",
                _format_date(raw_date),
                article.get("url") or "—",
            )

        console.print(sources_table)

    print_tip()


if __name__ == "__main__":
    app()
