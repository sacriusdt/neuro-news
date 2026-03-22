# Neuro News

Your AI-powered news terminal. Neuro News pulls articles from RSS feeds into a local SQLite database, lets you search them with rich filters, and answers natural-language questions about them using an LLM of your choice.

---

## Installation

### Recommended — pipx

[pipx](https://pipx.pypa.io) installs Python CLI tools in isolation and puts them on your PATH automatically, on every OS.

```bash
pipx install .
```

That's it. `neuro-news` is now available everywhere in your terminal.

> Don't have pipx? `pip install pipx` then `pipx ensurepath` (one-time setup).

### Alternative — virtual environment

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

pip install -e .
```

`neuro-news` works as long as the venv is active.

### Fallback — no install needed

```bash
python -m neuro_news <command>
```

Works anywhere without installing anything, as long as dependencies are installed (`pip install -r requirements.txt`).

---

## Quick start

```bash
# 1. Set up the database and load feeds
neuro-news init

# 2. Fetch articles once
neuro-news fetch

# 3. Start watching (polls every 5 minutes)
neuro-news watch

# 4. See all commands
neuro-news commands
```

---

## Commands

| Command | Description |
|---|---|
| `init` | Create the database and load feeds from `feeds.json` |
| `fetch` | Pull the latest articles from all feeds |
| `watch` | Continuously fetch on an interval (default: 5 min) |
| `search` | Search articles with optional filters |
| `chat` | Ask a natural-language question |
| `stats` | Show a snapshot of the database |
| `feeds list` | List all configured RSS feeds |
| `feeds add` | Add a new RSS feed |
| `streams list` | List all saved search streams |
| `streams create` | Create a new saved search stream |
| `streams run` | Run a saved stream |
| `streams delete` | Delete a saved stream |
| `commands` | Show this command menu in the terminal |

Run any command with `--help` for full details.

---

## Search

```bash
# Keyword search
neuro-news search "AI"

# Filter by category
neuro-news search "AI" --category Technology

# Filter by country
neuro-news search "climate" --country "United States"

# Filter by subcategory
neuro-news search --subcategory "Machine Learning"

# Date range
neuro-news search "stocks" --since 2024-01-01 --until 2024-12-31

# Filter by feed name
neuro-news search --feed "BBC" --limit 10

# Combine filters freely
neuro-news search "startup" --category Business --country "United States" --limit 5
```

### Available search options

| Option | Description |
|---|---|
| `--feed <title>` | Filter by feed name |
| `--category <name>` | Filter by category |
| `--subcategory <name>` | Filter by subcategory |
| `--country <name>` | Filter by country |
| `--since <date>` | Only articles after this date (`YYYY-MM-DD`) |
| `--until <date>` | Only articles before this date (`YYYY-MM-DD`) |
| `--limit <n>` | Maximum number of results |

---

## Chat

Ask questions in plain language. The chatbot searches the database, then answers with numbered citations.

```bash
neuro-news chat "What happened in AI this week?"
neuro-news chat "Latest gaming news from the US" --limit 5
neuro-news chat "Any news about OpenAI?" --provider anthropic
neuro-news chat "Tech acquisitions this month" --model gpt-4o
```

The chat pipeline works in two steps:
1. The LLM extracts search parameters from your question (keywords, filters, date range)
2. It searches the database and generates an answer with `[n]` citations

---

## Streams

Streams are saved searches you can replay at any time.

```bash
# Create a stream
neuro-news streams create ai-weekly --query "AI" --category Technology

# Run it
neuro-news streams run ai-weekly

# With a result limit
neuro-news streams run ai-weekly --limit 10

# List all streams
neuro-news streams list

# Delete a stream
neuro-news streams delete ai-weekly
```

---

## Configuration

A config file is created automatically on first run at:

```
~/.config/neuro-news/neuro-news/config.json   (Linux/macOS)
%LOCALAPPDATA%\neuro-news\neuro-news\config.json   (Windows)
```

### Environment variables

All settings can be overridden via a `.env` file in the project directory or as real environment variables.

| Variable | Description | Default |
|---|---|---|
| `NEURO_NEWS_PROVIDER` | LLM provider (`openai`, `anthropic`, `openrouter`) | `openrouter` |
| `NEURO_NEWS_MODEL` | Override the default model for the provider | provider default |
| `NEURO_NEWS_DB_PATH` | Custom path to the SQLite database | platform default |
| `NEURO_NEWS_POLL_INTERVAL` | Fetch interval in minutes for `watch` | `5` |
| `NEURO_NEWS_MAX_RESULTS` | Default result limit for search and chat | `20` |
| `NEURO_NEWS_TIMEOUT` | HTTP timeout in seconds | `20` |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `OPENROUTER_API_KEY` | OpenRouter API key | — |

### Default models

| Provider | Default model |
|---|---|
| `openai` | `gpt-4o-mini` |
| `anthropic` | `claude-3-5-sonnet-20240620` |
| `openrouter` | `anthropic/claude-3.5-sonnet` |

### Example `.env`

```env
OPENROUTER_API_KEY=sk-or-v1-...
NEURO_NEWS_PROVIDER=openrouter
NEURO_NEWS_MODEL=anthropic/claude-3.5-sonnet
NEURO_NEWS_POLL_INTERVAL=10
```

---

## Feeds

Feeds are defined in `feeds.json` at the root of the project. Each entry has:

```json
{
  "title": "The Verge",
  "url": "https://www.theverge.com/rss/index.xml",
  "category": "Technology",
  "country": "United States",
  "subcategories": ["AI", "Gadgets"]
}
```

You can also add a feed from the CLI:

```bash
neuro-news feeds add "My Feed" "https://example.com/rss" --category "Technology" --country "United States" --subcategory "AI"
```

After editing `feeds.json`, re-run `neuro-news init` to reload. Existing articles are not deleted.

---

## Notes

- Only RSS title and summary are stored — no full article scraping.
- Deduplication is done via SHA256 hash of `guid + url + title + published_at`.
- The database uses SQLite FTS5 for full-text search.
- `mega-feeds.json` is an extended feed list included for future use.
