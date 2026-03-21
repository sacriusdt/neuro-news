# Neuro News

Neuro News is a CLI-first RSS aggregator. It pulls articles from a curated list of feeds, stores them in a local SQLite database, and lets you search with filters. It also includes a built-in chatbot that reads the database and answers questions with citations.

## Quick start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Initialize the database and load feeds:

```bash
python -m neuro\_news init --feeds-path feeds.json
```

3. Fetch once:

```bash
python -m neuro\_news fetch
```

4. Watch (poll every 5 minutes by default):

```bash
python -m neuro\_news watch
```

## Search examples

```bash
python -m neuro\_news search "gaming" --country "United States"
python -m neuro\_news search "ai" --category "Technology" --limit 10
```

## Custom streams

```bash
python -m neuro\_news streams create "us-gaming" --query "gaming" --country "United States"
python -m neuro\_news streams list
python -m neuro\_news streams run "us-gaming" --limit 5
python -m neuro\_news streams delete "us-gaming"
```

## Chatbot

```bash
python -m neuro\_news chat "Give me the 5 latest gaming articles in the United States"
```

The chatbot runs a search behind the scenes and answers with citations.

## Configuration

A config file is created automatically on first run. You can override with env vars:

* `NEURO\_NEWS\_DB\_PATH`
* `NEURO\_NEWS\_PROVIDER` (openai, anthropic, openrouter)
* `NEURO\_NEWS\_MODEL`
* `NEURO\_NEWS\_POLL\_INTERVAL`
* `NEURO\_NEWS\_MAX\_RESULTS`
* `NEURO\_NEWS\_TIMEOUT`
* `OPENAI\_API\_KEY`
* `ANTHROPIC\_API\_KEY`
* `OPENROUTER\_API\_KEY`

## Notes

* This version uses `feeds.json`. `mega-feeds.json` is intentionally not used yet.
* Only RSS title/summary is stored (no full article scraping).

