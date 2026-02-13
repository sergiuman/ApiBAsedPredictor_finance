# News + Market Daily Signal

A Python script that combines news sentiment analysis with market technical indicators to produce a daily directional signal for a configured stock ticker.

**DISCLAIMER:** This tool is for informational and educational purposes only. It does NOT constitute financial advice, investment recommendation, or a solicitation to buy or sell any security. Always do your own research and consult a qualified financial advisor before making investment decisions.

## How It Works

1. **News ingestion** - Pulls recent headlines about a configured topic via NewsAPI.org (if key provided) or RSS feeds (Google News, Bing News, Yahoo Finance) as fallback.
2. **Market data** - Fetches historical price data via `yfinance` and computes simple indicators (7-day SMA, 21-day SMA, 7-day return).
3. **AI analysis** - Sends headlines + market data to OpenAI for sentiment analysis, key driver extraction, and directional bias estimation.
4. **Signal combination** - Combines the AI bias with technical trend confirmation:
   - AI says `likely_up` AND price > 7d SMA AND 7d return > 0 → **LIKELY UP**
   - AI says `likely_down` AND price < 7d SMA AND 7d return < 0 → **LIKELY DOWN**
   - Otherwise → **UNCERTAIN**
5. **Output** - Prints a formatted report to the console and optionally sends it to Telegram.

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
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY (required) + other keys (optional)

# 4. Run the script
python src/main.py
```

Or use the Makefile:

```bash
make setup       # Create venv + install deps
source .venv/bin/activate
cp .env.example .env
# Edit .env ...
make run         # Run the signal script
make test        # Run tests
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | **Yes** | - | Your OpenAI API key |
| `TOPIC` | No | `Microsoft` | News search topic |
| `TICKER` | No | `MSFT` | Stock ticker symbol |
| `NEWS_LOOKBACK_HOURS` | No | `24` | How far back to search for news |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model to use |
| `NEWSAPI_KEY` | No | - | NewsAPI.org key for better news coverage |
| `TELEGRAM_BOT_TOKEN` | No | - | Telegram bot token (from @BotFather) |
| `TELEGRAM_CHAT_ID` | No | - | Telegram chat ID (from @userinfobot) |

## Project Structure

```
├── .env.example                 # Template for environment variables
├── .github/workflows/daily.yml  # GitHub Actions cron workflow
├── Makefile                     # Convenience commands
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── data/                        # Local cache (auto-created, gitignored)
├── src/
│   ├── __init__.py
│   ├── main.py                  # Entry point - orchestrates pipeline
│   ├── news.py                  # News ingestion (NewsAPI + RSS)
│   ├── market.py                # Market data via yfinance
│   ├── ai_analyze.py            # OpenAI analysis + JSON validation
│   ├── notify.py                # Telegram notifications
│   └── utils.py                 # Config, logging, constants
└── tests/
    ├── __init__.py
    └── test_smoke.py            # Smoke tests
```

## Scheduling

### Option A: Run Manually in Codespace

Open a terminal in your GitHub Codespace and run:

```bash
source .venv/bin/activate
python src/main.py
```

### Option B: GitHub Actions Cron

A workflow file is included at `.github/workflows/daily.yml` that runs the script every weekday at 09:00 UTC.

**Setup steps:**

1. Go to your repository **Settings → Secrets and variables → Actions**.
2. Add the following repository secrets:
   - `OPENAI_API_KEY` (required)
   - `TELEGRAM_BOT_TOKEN` (optional, for notifications)
   - `TELEGRAM_CHAT_ID` (optional, for notifications)
   - `NEWSAPI_KEY` (optional, for better news)
   - `TOPIC` (optional, defaults to "Microsoft")
   - `TICKER` (optional, defaults to "MSFT")
3. The workflow runs automatically on weekdays at 09:00 UTC, or you can trigger it manually from the **Actions** tab.

## Telegram Setup (Optional)

1. Message [@BotFather](https://t.me/BotFather) on Telegram and create a new bot. Copy the bot token.
2. Message [@userinfobot](https://t.me/userinfobot) to get your chat ID.
3. Start a chat with your new bot (send it `/start`).
4. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to your `.env` file.

## Testing

```bash
python -m pytest tests/ -v
```

## Notes

- Without a `NEWSAPI_KEY`, the script falls back to RSS feeds which may have less coverage.
- Without an `OPENAI_API_KEY`, the script will exit with an error.
- The `data/` directory stores cached JSON files for debugging (last news fetch, last market data). These are not required and can be deleted at any time.
- The AI analysis includes retry logic: if the first API call returns invalid JSON, it retries once with a stricter prompt, then falls back to rule-based analysis.
