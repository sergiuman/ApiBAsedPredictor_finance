# News + Market Daily Signal

A Python pipeline that combines news sentiment analysis with market technical indicators to produce a daily directional signal for a configured stock ticker.

**DISCLAIMER:** This tool is for informational and educational purposes only. It does NOT constitute financial advice, investment recommendation, or a solicitation to buy or sell any security. Always do your own research and consult a qualified financial advisor before making investment decisions.

## How It Works

1. **News ingestion** — Pulls recent headlines via NewsAPI.org (if key provided) or RSS feeds (Google News, Bing News, Yahoo Finance) as fallback. Optional VADER sentiment pre-filter drops near-neutral headlines to save tokens.
2. **Market data** — Fetches historical prices via `yfinance` and computes: 7-day SMA, 21-day SMA, 7-day return, RSI-14, Bollinger Bands (20-day), and 10-day average volume.
3. **AI analysis** — Sends headlines + market indicators to OpenAI for sentiment analysis, key driver extraction, and directional bias estimation with confidence score.
4. **Signal combination** — Merges AI bias with technical confirmation:
   - AI `likely_up` + above SMA-7 + 7d return > 0 + confidence ≥ 70 → **HIGH CONVICTION UP**
   - AI `likely_up` + above SMA-7 + 7d return > 0 → **LIKELY UP**
   - AI `likely_down` + below SMA-7 + 7d return < 0 + confidence ≥ 70 → **HIGH CONVICTION DOWN**
   - AI `likely_down` + below SMA-7 + 7d return < 0 → **LIKELY DOWN**
   - Otherwise → **UNCERTAIN**
5. **Output** — Prints a formatted report, appends a record to `data/signal_history.jsonl`, and optionally sends to Telegram.

## Setup

### Prerequisites

- Python 3.11+
- An OpenAI API key ([get one here](https://platform.openai.com/api-keys))

### Quick Start

```bash
# 1. Clone the repository
git clone <repo-url> && cd ApiBAsedPredictor_finance

# 2. Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY (required) + other keys (optional)

# 4. Run
python src/main.py          # CLI pipeline
# or
streamlit run src/app.py   # Interactive Streamlit UI
```

Or use the Makefile:

```bash
make setup       # Create venv + install deps
source .venv/bin/activate
cp .env.example .env
# Edit .env ...
make run         # Run the CLI pipeline
make ui          # Launch the Streamlit UI
make test        # Run tests
make backtest    # Compare past signals to actual returns
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | **Yes** | — | Your OpenAI API key |
| `TOPIC` | No | `Microsoft` | News search topic |
| `TICKER` | No | `MSFT` | Stock ticker symbol |
| `NEWS_LOOKBACK_HOURS` | No | `24` | How far back to search for news |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model to use |
| `NEWSAPI_KEY` | No | — | NewsAPI.org key for better news coverage |
| `CONFIDENCE_THRESHOLD` | No | `40` | AI confidence below this → overrides bias to `uncertain` |
| `PRE_FILTER_SENTIMENT` | No | `false` | Enable VADER pre-filter to drop near-neutral headlines |
| `SENTIMENT_FILTER_THRESHOLD` | No | `0.05` | VADER compound score cutoff (used when pre-filter is on) |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token (from @BotFather) |
| `TELEGRAM_CHAT_ID` | No | — | Telegram chat ID (from @userinfobot) |

## Project Structure

```
├── .env.example                 # Template for environment variables
├── .github/workflows/daily.yml  # GitHub Actions cron workflow
├── Makefile                     # Convenience commands
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── data/                        # Local cache (auto-created, gitignored)
│   ├── last_news.json           # Cached last news fetch (debug)
│   ├── last_market.json         # Cached last market fetch (debug)
│   └── signal_history.jsonl    # Appended each run; used for backtest
├── src/
│   ├── __init__.py
│   ├── main.py                  # Entry point — orchestrates pipeline
│   ├── app.py                   # Streamlit interactive UI (make ui)
│   ├── news.py                  # News ingestion (NewsAPI + RSS + VADER filter)
│   ├── market.py                # Market data + RSI, Bollinger Bands, volume
│   ├── ai_analyze.py            # OpenAI analysis + confidence threshold filter
│   ├── history.py               # Signal history writer + backtest runner
│   ├── notify.py                # Telegram notifications
│   └── utils.py                 # Config, logging, constants
└── tests/
    ├── __init__.py
    └── test_smoke.py            # 65 smoke tests (all must pass)
```

## Scheduling

### Option A: Run Manually

```bash
source .venv/bin/activate
python src/main.py
```

### Option B: GitHub Actions Cron

A workflow at `.github/workflows/daily.yml` runs the script every weekday at 09:00 UTC.

**Setup steps:**

1. Go to your repository **Settings → Secrets and variables → Actions**.
2. Add the following repository secrets:
   - `OPENAI_API_KEY` (required)
   - `TELEGRAM_BOT_TOKEN` (optional)
   - `TELEGRAM_CHAT_ID` (optional)
   - `NEWSAPI_KEY` (optional)
   - `TOPIC` (optional, defaults to `Microsoft`)
   - `TICKER` (optional, defaults to `MSFT`)
3. The workflow runs automatically on weekdays at 09:00 UTC, or trigger it manually from the **Actions** tab.

## Telegram Setup (Optional)

1. Message [@BotFather](https://t.me/BotFather) and create a new bot. Copy the bot token.
2. Message [@userinfobot](https://t.me/userinfobot) to get your chat ID.
3. Start a chat with your new bot (send it `/start`).
4. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to your `.env` file.

## Backtesting

After accumulating a few runs, compare past signals to actual next-day returns:

```bash
make backtest
# or
python src/history.py
```

Each run appends one record to `data/signal_history.jsonl`. The backtest fetches next-day prices from yfinance and prints an accuracy table. Skips signals that are too recent (next-day data not yet available).

## Testing

```bash
python -m pytest tests/ -v   # all 65 tests must pass
```

## Notes

- Without a `NEWSAPI_KEY`, the script falls back to RSS feeds which may have less coverage.
- The AI analysis uses OpenAI's JSON mode to guarantee valid output, with a stricter-prompt retry and a rule-based fallback if both attempts fail.
- The `data/` directory stores cached JSON files for debugging and signal history. It is gitignored and can be deleted safely (except `signal_history.jsonl` if you want to keep backtest history).
