"""Entry point: News + Market Daily Signal script."""

from __future__ import annotations

import argparse
import sys
import logging
from datetime import datetime, timezone

from src.utils import Config, DISCLAIMER, logger
from src.news import fetch_news, Article
from src.market import fetch_market_data, MarketData
from src.ai_analyze import analyze, AnalysisResult
from src.notify import send_telegram
from src.history import append_signal_record, query_history_by_ticker, format_history_table


_HIGH_CONVICTION_THRESHOLD = 70


def combine_signals(ai: AnalysisResult, market: MarketData) -> str:
    """Combine AI directional bias with technical trend for final signal.

    Rules:
    - AI=likely_up AND above SMA7 AND return>0 AND confidence>=70 => high_conviction_up
    - AI=likely_up AND above SMA7 AND return>0                     => likely_up
    - AI=likely_down AND below SMA7 AND return<0 AND confidence>=70 => high_conviction_down
    - AI=likely_down AND below SMA7 AND return<0                    => likely_down
    - Otherwise => uncertain
    """
    bullish = (
        ai.directional_bias == "likely_up"
        and market.close_vs_sma7 == "above"
        and market.return_7d_pct > 0
    )
    bearish = (
        ai.directional_bias == "likely_down"
        and market.close_vs_sma7 == "below"
        and market.return_7d_pct < 0
    )
    high_conviction = ai.confidence_0_100 >= _HIGH_CONVICTION_THRESHOLD

    if bullish:
        return "high_conviction_up" if high_conviction else "likely_up"
    elif bearish:
        return "high_conviction_down" if high_conviction else "likely_down"
    else:
        return "uncertain"


def format_signal_label(signal: str) -> str:
    """Human-readable signal label."""
    labels = {
        "likely_up": "LIKELY UP",
        "likely_down": "LIKELY DOWN",
        "uncertain": "UNCERTAIN",
        "high_conviction_up": "HIGH CONVICTION UP",
        "high_conviction_down": "HIGH CONVICTION DOWN",
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

    past_records = query_history_by_ticker(cfg, cfg.ticker)
    history_table = format_history_table(past_records)

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

--- PAST PREDICTIONS ({cfg.ticker}) ---
{history_table}

--- FINAL SIGNAL ---
>>> {signal_label} <<<

{'='*60}
{DISCLAIMER}
{'='*60}
"""
    return report.strip()


def run_pipeline(
    cfg: Config,
) -> tuple[list[Article], MarketData, AnalysisResult, str, str]:
    """Run the analysis pipeline and return (articles, market, ai_result, final_signal, report).

    Raises ValueError on market data failure so callers (Streamlit, tests) can
    handle errors gracefully without triggering sys.exit().
    """
    # 1. Fetch news
    try:
        articles = fetch_news(cfg)
    except Exception as exc:
        logger.error("Failed to fetch news: %s", exc)
        articles = []

    if not articles:
        logger.warning("No news articles found. Analysis will rely on market data only.")

    # 2. Fetch market data — raise on failure (no sys.exit here)
    try:
        market = fetch_market_data(cfg)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Unexpected error fetching market data: {exc}") from exc

    # 3. AI analysis
    ai_result = analyze(articles, market, cfg)

    # 4. Combine signals
    final_signal = combine_signals(ai_result, market)

    # 5. Build report
    report = build_report(cfg, articles, market, ai_result, final_signal)

    return articles, market, ai_result, final_signal, report


def main() -> None:
    """Run the daily signal pipeline (CLI entry point)."""
    parser = argparse.ArgumentParser(description="News + Market Daily Signal")
    parser.add_argument(
        "--history",
        metavar="TICKER",
        help="Print past predictions for TICKER and exit",
    )
    args = parser.parse_args()

    if args.history:
        cfg = Config()
        print(format_history_table(query_history_by_ticker(cfg, args.history)))
        return

    logger.info("Starting News + Market Daily Signal")

    # 1. Load and validate config
    cfg = Config()
    problems = cfg.validate()
    if problems:
        for p in problems:
            logger.error("Config error: %s", p)
        logger.error("Fix the above issues in your .env file and retry.")
        sys.exit(1)

    # 2-5. Run pipeline
    try:
        articles, market, ai_result, final_signal, report = run_pipeline(cfg)
    except ValueError as exc:
        logger.error("Pipeline error: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.error("Unexpected pipeline error: %s", exc)
        sys.exit(1)

    # 5a. Persist signal record for history / backtest
    append_signal_record(cfg, market, ai_result, final_signal)

    # 6. Print report
    print(report)

    # 7. Send to Telegram (optional)
    send_telegram(report, cfg)

    logger.info("Done.")


if __name__ == "__main__":
    main()
