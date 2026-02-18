# CLAUDE.md — Agent Team Guide

This file is the authoritative reference for Claude agents working on this project.
Read it fully before making any changes.

---

## Project Overview

**News + Market Daily Signal** — A Python pipeline that:
1. Fetches recent news headlines (NewsAPI or RSS fallback)
2. Pulls stock market indicators via yfinance
3. Sends both to OpenAI for sentiment + bias analysis
4. Combines AI output with technical indicators into a final signal: `LIKELY UP`, `LIKELY DOWN`, or `UNCERTAIN`
5. Prints a formatted report and optionally sends it to Telegram

**This is a financial analysis tool. All output must include the disclaimer from `src/utils.py:DISCLAIMER`.**

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Market data | `yfinance` |
| News | `requests` (NewsAPI) + `feedparser` (RSS) |
| AI | OpenAI API (`openai>=1.0.0`) |
| Notifications | Telegram Bot API |
| Config | `python-dotenv` |
| Tests | `pytest` |
| CI | GitHub Actions (`.github/workflows/daily.yml`) |

---

## Repository Layout

```
ApiBAsedPredictor_finance/
├── CLAUDE.md                        # This file — agent guide
├── README.md                        # User-facing documentation
├── .env.example                     # All configurable env vars with defaults
├── .github/workflows/daily.yml      # GitHub Actions cron (weekdays 09:00 UTC)
├── Makefile                         # make setup | run | test | clean
├── requirements.txt                 # Runtime + dev dependencies
├── data/                            # Auto-created cache dir (gitignored)
│   ├── last_news.json               # Cached last news fetch (debug)
│   └── last_market.json             # Cached last market fetch (debug)
├── docs/
│   └── ROADMAP.md                   # Future features, agent-assignable tasks
├── src/
│   ├── __init__.py
│   ├── main.py                      # Entry point: orchestrates the 7-step pipeline
│   ├── news.py                      # News ingestion + deduplication
│   ├── market.py                    # Market data + indicators (SMA7, SMA21, 7d return)
│   ├── ai_analyze.py                # OpenAI prompt, JSON parsing, rule-based fallback
│   ├── notify.py                    # Telegram notification sender
│   └── utils.py                     # Config dataclass, logger, DISCLAIMER constant
└── tests/
    ├── __init__.py
    └── test_smoke.py                # Unit tests — must pass before any PR
```

---

## Key Commands

```bash
# Environment setup
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Or using Makefile
make setup
make run                           # python src/main.py
make test                          # pytest tests/ -v
make clean                         # remove .venv, caches, __pycache__

# Run tests directly
python -m pytest tests/ -v
python -m pytest tests/ -v -k "TestCombineSignals"   # Run specific class
```

Always run tests with `python -m pytest tests/ -v` before submitting changes.
**All tests must pass.** There are no known expected failures.

---

## Environment Variables

Defined in `src/utils.py:Config`. All loaded from `.env` at project root.

| Variable | Required | Default | Notes |
|---|---|---|---|
| `OPENAI_API_KEY` | **Yes** | — | Script exits if missing |
| `TOPIC` | No | `Microsoft` | News search topic |
| `TICKER` | No | `MSFT` | Stock ticker symbol |
| `NEWS_LOOKBACK_HOURS` | No | `24` | Rolling news window |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Any chat-completion model |
| `NEWSAPI_KEY` | No | — | NewsAPI.org key; RSS used if absent |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | No | — | Telegram chat ID |

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

---

## Architecture: Data Flow

```
Config (utils.py)
    │
    ├─► fetch_news(cfg)          → list[Article]         (news.py)
    │       NewsAPI → RSS fallback
    │       Dedup by URL+title SHA256
    │       Filter by lookback window
    │
    ├─► fetch_market_data(cfg)   → MarketData            (market.py)
    │       yfinance 3-month history
    │       Computes: sma_7, sma_21, close_vs_sma7, return_7d_pct
    │
    ├─► analyze(articles, market, cfg) → AnalysisResult  (ai_analyze.py)
    │       Build prompt (top 30 headlines + market indicators)
    │       Call OpenAI (2 attempts, stricter prompt on retry)
    │       Parse + validate JSON → AnalysisResult
    │       Falls back to _rule_based_fallback() if both attempts fail
    │
    ├─► combine_signals(ai, market)    → str             (main.py)
    │       "likely_up"   if AI=up   AND above SMA7 AND return>0
    │       "likely_down" if AI=down AND below SMA7 AND return<0
    │       "uncertain"   otherwise
    │
    ├─► build_report(...)             → str              (main.py)
    │
    └─► send_telegram(report, cfg)                       (notify.py)
```

---

## Key Data Models

### `Article` (src/news.py)
```python
@dataclass
class Article:
    title: str
    source: str
    published: str    # ISO-8601
    summary: str
    url: str
```

### `MarketData` (src/market.py)
```python
@dataclass
class MarketData:
    ticker: str
    last_close: float
    last_close_date: str
    sma_7: float
    sma_21: float
    close_vs_sma7: str          # "above" | "below"
    return_7d_pct: float
    prices_available: int
```

### `AnalysisResult` (src/ai_analyze.py)
```python
@dataclass
class AnalysisResult:
    news_sentiment: str         # "positive" | "negative" | "mixed" | "neutral"
    key_drivers: list[str]      # 1-5 items
    risk_factors: list[str]     # 1-5 items
    directional_bias: str       # "likely_up" | "likely_down" | "uncertain"
    confidence_0_100: int       # 0-100, clamped
    one_paragraph_rationale: str
```

### `Config` (src/utils.py)
Loaded via `Config()` — reads env vars, creates `data/` dir, exposes `validate()`.

---

## Coding Conventions

- **Python 3.11+ features** — use `from __future__ import annotations`, `dataclasses`, type hints
- **Module-level loggers** — `logger = logging.getLogger("signal.<module>")`, not `print()`
- **Graceful degradation** — news fails → empty list; AI fails → rule-based fallback; Telegram fails → log only
- **No bare `except`** — always catch specific exceptions or `Exception` with logging
- **Constants uppercase** — `VALID_SENTIMENTS`, `DISCLAIMER`, `_NEWSAPI_URL`
- **Private helpers prefixed `_`** — e.g., `_fetch_rss`, `_parse_analysis`, `_rule_based_fallback`
- **Data caching** — write JSON to `cfg.data_dir` for debugging after each fetch; swallow cache write errors
- **AI prompts** — always request raw JSON (no markdown fences), validate all fields, clamp numerics
- **Financial disclaimer** — the `DISCLAIMER` constant from `utils.py` must appear in every report output

---

## Testing Conventions

Tests live in `tests/test_smoke.py`. Organized by class:

| Class | What it tests |
|---|---|
| `TestConfig` | Config defaults, validation |
| `TestNewsDedupe` | Article deduplication logic |
| `TestAIParser` | JSON parsing, markdown fence stripping, clamping |
| `TestRuleBased` | Rule-based fallback analysis |
| `TestCombineSignals` | Signal combination logic (all 4 scenarios) |
| `TestDisclaimer` | Disclaimer presence and content |

When adding new features, add tests to the relevant class or create a new class.
Tests use `unittest.mock` — do not make real API calls in tests.

---

## Common Agent Tasks

### Adding a new indicator to MarketData
1. Add field to `MarketData` dataclass in `src/market.py`
2. Compute and assign in `fetch_market_data()`
3. Include in `market_info` dict in `src/ai_analyze.py:_build_prompt()`
4. Update report format in `src/main.py:build_report()` if user-visible
5. Add test coverage in `TestRuleBased` or a new test class

### Adding a new news source
1. Add to `_RSS_FEEDS` list in `src/news.py` or add a new `_fetch_<source>()` function
2. Call it in `fetch_news()` with appropriate fallback logic
3. Ensure `_deduplicate()` handles duplicates across sources

### Changing the AI prompt
1. Edit `_build_prompt()` in `src/ai_analyze.py`
2. Also update `_build_strict_retry_prompt()` if the schema changes
3. Update `_parse_analysis()` if new fields are added to `AnalysisResult`
4. Update `TestAIParser` tests

### Adding a new notification channel
1. Create `src/notify_<channel>.py` following the pattern in `src/notify.py`
2. Add config fields to `Config` in `src/utils.py`
3. Add to `.env.example`
4. Call from `src/main.py:main()` after `send_telegram()`

### Modifying signal combination logic
1. Edit `combine_signals()` in `src/main.py`
2. Update ALL test cases in `TestCombineSignals` — these are specification tests

---

## Resilience & Fallback Chain

```
News:    NewsAPI → RSS (Google News + Bing News + Yahoo Finance) → empty list
AI:      OpenAI attempt 1 → OpenAI attempt 2 (stricter prompt) → rule-based fallback
Notify:  Telegram send → log error, continue (never crash)
```

The pipeline always produces a report even with no news or no AI access.

---

## CI / GitHub Actions

Workflow: `.github/workflows/daily.yml`
- Runs weekdays at 09:00 UTC (`cron: '0 9 * * 1-5'`)
- Can be triggered manually from GitHub Actions tab
- Secrets needed: `OPENAI_API_KEY`, optionally `NEWSAPI_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TOPIC`, `TICKER`

---

## What NOT To Do

- Never commit `.env` or any file containing API keys
- Never remove the `DISCLAIMER` from report output
- Never add financial advice wording to the report
- Never make real API calls in unit tests (use mocks)
- Never `sys.exit()` from a module other than `main.py`
- Never swallow exceptions silently without at least a `logger.warning()`

---

## Future Development

See `docs/ROADMAP.md` for the structured list of planned features organized by domain.
