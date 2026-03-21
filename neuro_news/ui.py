from __future__ import annotations

import random
from contextlib import contextmanager
from typing import Generator

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# ---------------------------------------------------------------------------
# Random tips
# ---------------------------------------------------------------------------

TIPS: list[str] = [
    "Use [bold cyan]search --category Technology[/] to filter articles by category.",
    "Save frequent searches with [bold cyan]streams create <name>[/] — run them anytime.",
    "Ask natural-language questions with [bold cyan]chat \"what happened in AI this week?\"[/]",
    "Filter by country: [bold cyan]search --country \"United States\"[/]",
    "Run [bold cyan]watch[/] to continuously pull new articles every few minutes.",
    "Combine filters: [bold cyan]search --category Finance --since 2024-01-01[/]",
    "Switch AI providers with [bold cyan]chat --provider anthropic[/]",
    "Use [bold cyan]feeds list[/] to browse all your RSS sources.",
    "Narrow results by feed: [bold cyan]search --feed BBC[/]",
    "Run [bold cyan]neuro-news commands[/] (or just [bold cyan]neuro-news[/]) to see every command at a glance.",
    "Run [bold cyan]stats[/] to get a quick snapshot of your database.",
    "Use [bold cyan]streams run <name>[/] to replay a saved search instantly.",
    "Set [bold cyan]NEURO_NEWS_MODEL[/] in your .env to lock in a default model.",
    "Pass [bold cyan]--limit 5[/] to any search or chat to keep output focused.",
    "Use [bold cyan]search --subcategory AI[/] to drill into subcategories.",
]


def get_random_tip() -> str:
    return random.choice(TIPS)


def print_tip() -> None:
    tip = get_random_tip()
    console.print(f"\n[dim]Tip:[/] {tip}")


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

BANNER = r"""
  _   _                      _   _
 | \ | | ___ _   _ _ __ ___ | \ | | _____      _____
 |  \| |/ _ \ | | | '__/ _ \|  \| |/ _ \ \ /\ / / __|
 | |\  |  __/ |_| | | | (_) | |\  |  __/\ V  V /\__ \
 |_| \_|\___|\__,_|_|  \___/|_| \_|\___| \_/\_/ |___/
"""


def print_banner(version: str = "0.1.0") -> None:
    text = Text(BANNER, style="bold cyan", justify="center")
    subtitle = Text(f"Your AI-powered news terminal  ·  v{version}", style="dim", justify="center")
    console.print(text)
    console.print(subtitle)
    console.print()


# ---------------------------------------------------------------------------
# Commands menu (shown by "/")
# ---------------------------------------------------------------------------

COMMANDS: list[tuple[str, str, str]] = [
    # (command, description, example)
    ("init", "Set up the database and load feeds", "neuro-news init"),
    ("fetch", "Pull the latest articles from all feeds", "neuro-news fetch"),
    ("watch", "Continuously fetch on an interval", "neuro-news watch --interval 10"),
    ("search", "Search articles with optional filters", 'neuro-news search "AI"'),
    ("chat", "Ask a natural-language question", 'neuro-news chat "Latest tech news?"'),
    ("stats", "Show database statistics", "neuro-news stats"),
    ("feeds list", "List all configured RSS feeds", "neuro-news feeds list"),
    ("streams list", "List all saved search streams", "neuro-news streams list"),
    ("streams create", "Create a new saved search stream", 'neuro-news streams create my-ai --query "AI"'),
    ("streams run", "Run a saved search stream", "neuro-news streams run my-ai"),
    ("streams delete", "Delete a saved stream", "neuro-news streams delete my-ai"),
]

SEARCH_OPTIONS: list[tuple[str, str]] = [
    ("--feed <title>", "Filter by feed name"),
    ("--category <name>", "Filter by category"),
    ("--subcategory <name>", "Filter by subcategory"),
    ("--country <name>", "Filter by country"),
    ("--since <date>", "Only articles after this date (YYYY-MM-DD)"),
    ("--until <date>", "Only articles before this date (YYYY-MM-DD)"),
    ("--limit <n>", "Limit the number of results"),
]


def show_commands_menu() -> None:
    print_banner()

    # Main commands table
    table = Table(
        title="[bold]Available Commands[/]",
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
        title_style="bold white",
        expand=True,
    )
    table.add_column("Command", style="bold cyan", no_wrap=True, min_width=20)
    table.add_column("Description", style="white")
    table.add_column("Example", style="dim green")

    for cmd, desc, example in COMMANDS:
        table.add_row(cmd, desc, example)

    console.print(table)
    console.print()

    # Search/filter options
    opts = Table(
        title="[bold]Search & Stream Filter Options[/]",
        show_header=True,
        header_style="bold magenta",
        border_style="dim",
        title_style="bold white",
    )
    opts.add_column("Option", style="bold yellow", no_wrap=True, min_width=22)
    opts.add_column("Description", style="white")

    for opt, desc in SEARCH_OPTIONS:
        opts.add_row(opt, desc)

    console.print(opts)
    console.print()
    console.print("[dim]Run any command with [bold]--help[/] for full details.[/]")
    console.print()


# ---------------------------------------------------------------------------
# Spinner context manager
# ---------------------------------------------------------------------------

@contextmanager
def spinner(message: str, style: str = "bold green") -> Generator[None, None, None]:
    with console.status(f"[{style}]{message}[/]", spinner="dots"):
        yield


# ---------------------------------------------------------------------------
# Styled output helpers
# ---------------------------------------------------------------------------

def print_success(message: str) -> None:
    console.print(f"[bold green]✓[/] {message}")


def print_info(message: str) -> None:
    console.print(f"[bold blue]ℹ[/] {message}")


def print_warning(message: str) -> None:
    console.print(f"[bold yellow]⚠[/] {message}")


def print_error(message: str) -> None:
    console.print(f"[bold red]✗[/] {message}")


def print_result_count(count: int, label: str = "result") -> None:
    noun = label if count == 1 else f"{label}s"
    color = "green" if count > 0 else "yellow"
    console.print(f"\n[{color}]{count} {noun} found.[/]")
