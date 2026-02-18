# Roadmap — Agent-Assignable Future Work

This document organizes planned features and improvements by domain.
Each item is scoped to be assignable to a single Claude agent team.
Items within each section are ordered from lower to higher complexity.

See `CLAUDE.md` for architecture, conventions, and agent task guides.

---

## Domain: Market Data (`src/market.py`)

### ~~M1 — Add RSI Indicator~~ ✅ DONE
**Goal:** Compute the 14-day Relative Strength Index and include it in `MarketData`.
**Acceptance:** `MarketData.rsi_14` field (float, 0-100). Report shows RSI. Tests cover boundary cases (overbought >70, oversold <30).
**Complexity:** Low — pure pandas math, no new dependencies.

### ~~M2 — Add Bollinger Bands~~ ✅ DONE
**Goal:** Compute 20-day Bollinger Bands (upper/lower/middle) and a `bb_position` field ("above_upper", "inside", "below_lower").
**Acceptance:** New fields on `MarketData`. Included in AI prompt. Tested.
**Complexity:** Low.

### ~~M3 — Add Volume Analysis~~ ✅ DONE
**Goal:** Include average 10-day volume and compare today's volume to the average.
**Acceptance:** `vol_10d_avg` and `vol_vs_avg` ("high" | "normal" | "low") fields on `MarketData`.
**Complexity:** Low.

### M4 — Multi-Ticker Support
**Goal:** Allow a comma-separated `TICKER` env var (e.g., `MSFT,AAPL,GOOGL`).
**Acceptance:** Pipeline runs once per ticker, produces one report per ticker, sends each to Telegram.
**Complexity:** Medium — requires refactoring `main.py` pipeline loop.

### M5 — Sector Comparison
**Goal:** Compare ticker performance to its sector ETF (e.g., XLK for tech).
**Acceptance:** `sector_relative_return_7d` field in `MarketData`. Included in AI prompt.
**Complexity:** Medium — requires ticker-to-sector mapping.

---

## Domain: News Ingestion (`src/news.py`)

### ~~N1 — Add Sentiment Pre-filter~~ ✅ DONE
**Goal:** Score each headline with VADER before sending to OpenAI. Filter out near-neutral articles to reduce token cost.
**Acceptance:** New optional `pre_filter_sentiment` config option. Tested with mocked VADER scores.
**Complexity:** Low — `vaderSentiment` or `textblob` is a small pip install.

### N2 — Alpha Vantage News Source
**Goal:** Add Alpha Vantage News Sentiment API as a third news source option (after NewsAPI, before RSS).
**Acceptance:** `_fetch_alphavantage(cfg)` function. Requires `ALPHAVANTAGE_KEY` env var. Gracefully skipped if key absent.
**Complexity:** Low.

### N3 — Article Relevance Scoring
**Goal:** Score articles by relevance to the ticker/topic before sending to OpenAI. Use simple keyword matching. Return only top N most relevant.
**Acceptance:** `_score_relevance(article, cfg)` helper. Config option `MAX_ARTICLES_TO_AI` (default 30, currently hardcoded).
**Complexity:** Low-Medium.

### N4 — Historical News Cache + Dedup Across Runs
**Goal:** Persist seen article hashes across runs (in `data/seen_articles.json`) so the same article is never sent to OpenAI twice.
**Acceptance:** Cache file managed in `fetch_news()`. Tests verify cross-run deduplication.
**Complexity:** Medium.

---

## Domain: AI Analysis (`src/ai_analyze.py`)

### ~~A1 — Structured Outputs / JSON Schema Enforcement~~ ✅ DONE
**Goal:** Use OpenAI's `response_format={"type": "json_object"}` to guarantee valid JSON and eliminate the retry+parse dance.
**Acceptance:** `_parse_analysis()` still validates fields but JSON parse errors should be eliminated. Tests updated.
**Complexity:** Low — one-line change to the API call.

### A2 — Confidence Threshold Filtering
**Goal:** If `confidence_0_100 < CONFIDENCE_THRESHOLD` (default 40, configurable), override `directional_bias` to `"uncertain"`.
**Acceptance:** New `CONFIDENCE_THRESHOLD` env var. Behavior tested.
**Complexity:** Low.

### A3 — Multi-Model Support
**Goal:** Support specifying multiple models in priority order (e.g., `OPENAI_MODEL=gpt-4o,gpt-4o-mini`). Fall back to next model on quota/rate errors.
**Acceptance:** Config parses comma-separated model list. Tested with mocked quota errors.
**Complexity:** Medium.

### A4 — Prompt Versioning
**Goal:** Move prompt templates to `src/prompts/` as `.txt` or `.jinja2` files. Load them at runtime. This makes prompt iteration easier for non-Python contributors.
**Acceptance:** All prompt strings moved out of `ai_analyze.py`. Behavior unchanged. Tests pass.
**Complexity:** Medium — requires adding Jinja2 or simple string templating.

### A5 — Alternative LLM Support (Anthropic / Local)
**Goal:** Abstract the AI client behind a protocol/interface so Anthropic Claude or a local Ollama model can be swapped in via `LLM_PROVIDER=openai|anthropic|ollama`.
**Acceptance:** New `src/llm.py` module with provider abstraction. `ai_analyze.py` uses it. Tests mock the interface.
**Complexity:** High — significant refactor.

---

## Domain: Signal Logic (`src/main.py`)

### ~~S1 — Confidence-Weighted Signal~~ ✅ DONE
**Goal:** Include `confidence_0_100` in the final signal decision. High-confidence AI + confirming technicals = stronger signal label.
**Acceptance:** New signal values `"high_conviction_up"` / `"high_conviction_down"` for confidence ≥ 70 with technical confirmation.
**Complexity:** Low.

### S2 — Signal History & Accuracy Tracking
**Goal:** Append each run's signal to `data/signal_history.jsonl`. After enough history, compare past signals to actual next-day returns.
**Acceptance:** `data/signal_history.jsonl` updated each run. Optional `make backtest` command to compute accuracy.
**Complexity:** Medium.

### S3 — Portfolio-Level Signal
**Goal:** Run the pipeline for multiple tickers and combine individual signals into a portfolio-level summary (e.g., "6/10 holdings bullish").
**Acceptance:** New `--portfolio` mode in `main.py`. Aggregated report printed and sent via Telegram.
**Complexity:** High — depends on M4 (multi-ticker support).

---

## Domain: Notifications (`src/notify.py`)

### NF1 — Email Notification
**Goal:** Send the report via SMTP email (Gmail App Password or SendGrid).
**Acceptance:** `send_email(report, cfg)` function. `EMAIL_TO`, `EMAIL_FROM`, `SMTP_HOST`, `SMTP_PASSWORD` env vars. Gracefully skipped if not configured.
**Complexity:** Low.

### NF2 — Slack Notification
**Goal:** Post the report to a Slack channel via Incoming Webhook.
**Acceptance:** `send_slack(report, cfg)` function. `SLACK_WEBHOOK_URL` env var.
**Complexity:** Low.

### NF3 — Discord Notification
**Goal:** Post the report to a Discord channel via webhook.
**Acceptance:** `send_discord(report, cfg)` function. `DISCORD_WEBHOOK_URL` env var.
**Complexity:** Low.

### NF4 — Rich Telegram Formatting
**Goal:** Format the Telegram message with Markdown (bold signal labels, code blocks for indicators) instead of plain text.
**Acceptance:** `parse_mode="MarkdownV2"` used. All special characters escaped. Visual output tested with screenshots.
**Complexity:** Medium — Telegram's MarkdownV2 escaping rules are finicky.

---

## Domain: Infrastructure & DX

### I1 — Pre-commit Hooks
**Goal:** Add `pre-commit` config to run `ruff` (linting) and `pytest` on every commit.
**Acceptance:** `.pre-commit-config.yaml` added. `make setup` installs hooks.
**Complexity:** Low.

### I2 — Type Checking with mypy
**Goal:** Add `mypy` to the test suite (`make typecheck`). Fix any existing type errors.
**Acceptance:** `mypy src/ tests/` exits with 0 errors. Added to CI.
**Complexity:** Low-Medium.

### I3 — Docker Support
**Goal:** Add `Dockerfile` and `docker-compose.yml` for containerized runs.
**Acceptance:** `docker compose up` runs the pipeline. `.env` passed via `env_file`. Data dir mounted as volume.
**Complexity:** Medium.

### I4 — Web Dashboard
**Goal:** Simple read-only HTML dashboard served by FastAPI that shows the last signal, history chart, and raw report.
**Acceptance:** `src/server.py` with FastAPI app. `make serve` command. Reads from `data/signal_history.jsonl`.
**Complexity:** High — new dependency (FastAPI, uvicorn), frontend HTML.

---

## Prioritization Guide for Agent Teams

**Start here (independent, low-risk):**
- A1 — Structured Outputs (improves reliability immediately)
- N1 — Sentiment Pre-filter (reduces AI cost)
- NF1/NF2/NF3 — Additional notification channels (fully additive)
- I1 — Pre-commit hooks (improves DX for all future work)

**Medium priority (build on core):**
- M1, M2, M3 — More indicators (more data = better AI analysis)
- S1 — Confidence-weighted signal (better signal quality)
- A2 — Confidence threshold filtering

**High priority (larger scope, do these after basics are solid):**
- M4 — Multi-ticker (enables portfolio features)
- S2 — Signal history (enables backtesting)
- I2 — Type checking (code quality)

**Long-term / high complexity:**
- A5 — Multi-LLM support
- S3 — Portfolio signal
- I4 — Web dashboard
