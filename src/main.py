"""Entry point: News + Market Daily Signal script."""

from __future__ import annotations

import sys
import logging
from datetime import datetime, timezone

from src.utils import Config, DISCLAIMER, logger
from src.news import fetch_news, Article
from src.market import fetch_market_data, MarketData
from src.ai_analyze import analyze, AnalysisResult
from src.notify import send_telegram


def combine_signals(ai: AnalysisResult, market: MarketData) -> str:
    """Combine AI directional bias with basic trend for final signal.

    Rules:
    - AI says likely_up AND close > 7d SMA AND 7d return > 0 => likely_up
    - AI says likely_down AND close < 7d SMA AND 7d return < 0 => likely_down
    - Otherwise => uncertain
    """
    if (
        ai.directional_bias == "likely_up"
        and market.close_vs_sma7 == "above"
        and market.return_7d_pct > 0
    ):
        return "likely_up"
    elif (
        ai.directional_bias == "likely_down"
        and market.close_vs_sma7 == "below"
        and market.return_7d_pct < 0
    ):
        return "likely_down"
    else:
        return "uncertain"


def format_signal_label(signal: str) -> str:
    """Human-readable signal label."""
    labels = {
        "likely_up": "LIKELY UP",
        "likely_down": "LIKELY DOWN",
        "uncertain": "UNCERTAIN",
    }
    return labels.get(signal, signal.upper())


def build_report(
    cfg: Config,
    articles: list[Article],
    market: MarketData,
    ai: AnalysisResult,
    final_signal: str,
) -> str:
    """Build the formatted report string."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    signal_label = format_signal_label(final_signal)

    drivers_str = "\n".join(f"  - {d}" for d in ai.key_drivers) if ai.key_drivers else "  (none)"
    risks_str = "\n".join(f"  - {r}" for r in ai.risk_factors) if ai.risk_factors else "  (none)"

    report = f"""
{'='*60}
  NEWS + MARKET DAILY SIGNAL
{'='*60}

Timestamp:     {now}
Topic:         {cfg.topic}
Ticker:        {cfg.ticker}
Articles used: {len(articles)}

--- MARKET INDICATORS ---
Last Close:      ${market.last_close} ({market.last_close_date})
7-Day SMA:       ${market.sma_7}
21-Day SMA:      ${market.sma_21}
Close vs 7d SMA: {market.close_vs_sma7.upper()}
7-Day Return:    {market.return_7d_pct}%
RSI (14):        {market.rsi_14}{"  ← overbought" if market.rsi_14 > 70 else "  ← oversold" if market.rsi_14 < 30 else ""}
BB Upper (20):   ${market.bb_upper}
BB Middle (20):  ${market.bb_middle}
BB Lower (20):   ${market.bb_lower}
BB Position:     {market.bb_position.replace("_", " ").upper()}
10-Day Avg Vol:  {market.vol_10d_avg:,.0f}
Vol vs Avg:      {market.vol_vs_avg.upper()}

--- AI ANALYSIS ---
News Sentiment:  {ai.news_sentiment.upper()}
AI Bias:         {ai.directional_bias}
AI Confidence:   {ai.confidence_0_100}/100

Key Drivers:
{drivers_str}

Risk Factors:
{risks_str}

Rationale:
  {ai.one_paragraph_rationale}

--- FINAL SIGNAL ---
>>> {signal_label} <<<

{'='*60}
{DISCLAIMER}
{'='*60}
"""
    return report.strip()


def main() -> None:
    """Run the daily signal pipeline."""
    logger.info("Starting News + Market Daily Signal")

    # 1. Load and validate config
    cfg = Config()
    problems = cfg.validate()
    if problems:
        for p in problems:
            logger.error("Config error: %s", p)
        logger.error("Fix the above issues in your .env file and retry.")
        sys.exit(1)

    # 2. Fetch news
    try:
        articles = fetch_news(cfg)
    except Exception as exc:
        logger.error("Failed to fetch news: %s", exc)
        articles = []

    if not articles:
        logger.warning("No news articles found. Analysis will rely on market data only.")

    # 3. Fetch market data
    try:
        market = fetch_market_data(cfg)
    except ValueError as exc:
        logger.error("Market data error: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Unexpected error fetching market data: %s", exc)
        sys.exit(1)

    # 4. AI analysis
    ai_result = analyze(articles, market, cfg)

    # 5. Combine signals
    final_signal = combine_signals(ai_result, market)

    # 6. Build and print report
    report = build_report(cfg, articles, market, ai_result, final_signal)
    print(report)

    # 7. Send to Telegram (optional)
    send_telegram(report, cfg)

    logger.info("Done.")


if __name__ == "__main__":
    main()
