"""Signal history — append run records and compute next-day accuracy via backtest."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import yfinance as yf

from src.market import MarketData
from src.ai_analyze import AnalysisResult
from src.utils import Config

logger = logging.getLogger("signal.history")

_HISTORY_FILE = "signal_history.jsonl"

# Signals that express a directional prediction (excluded: "uncertain")
_BULLISH_SIGNALS = {"likely_up", "high_conviction_up"}
_BEARISH_SIGNALS = {"likely_down", "high_conviction_down"}


def append_signal_record(
    cfg: Config,
    market: MarketData,
    ai: AnalysisResult,
    final_signal: str,
) -> None:
    """Append one run's output to data/signal_history.jsonl.

    Each line is a self-contained JSON object (JSONL format).
    Swallows write errors so a history failure never crashes the pipeline.
    """
    record = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "ticker": market.ticker,
        "topic": cfg.topic,
        "final_signal": final_signal,
        "confidence_0_100": ai.confidence_0_100,
        "news_sentiment": ai.news_sentiment,
        "directional_bias": ai.directional_bias,
        "last_close": market.last_close,
        "last_close_date": market.last_close_date,
        "return_7d_pct": market.return_7d_pct,
        "close_vs_sma7": market.close_vs_sma7,
        "rsi_14": market.rsi_14,
    }
    history_path = cfg.data_dir / _HISTORY_FILE
    try:
        with history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        logger.info("Signal record appended → %s", history_path)
    except OSError as exc:
        logger.warning("Could not write signal history: %s", exc)


def load_history(cfg: Config) -> list[dict]:
    """Read all records from data/signal_history.jsonl.

    Returns an empty list if the file does not exist.
    Skips and warns on malformed lines.
    """
    history_path = cfg.data_dir / _HISTORY_FILE
    if not history_path.exists():
        return []

    records: list[dict] = []
    with history_path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed history line %d: %s", lineno, exc)
    return records


def run_backtest(cfg: Config) -> None:
    """Compare past signals to actual next-day price moves.

    For each record in signal_history.jsonl:
      - Fetches the next trading day's close price via yfinance
      - Marks the signal correct/incorrect/excluded (uncertain)
      - Prints an accuracy summary table
    """
    records = load_history(cfg)
    if not records:
        print("No signal history found. Run the pipeline at least once.")
        return

    evaluated: list[dict] = []
    for rec in records:
        ticker = rec.get("ticker", "")
        close_date = rec.get("last_close_date", "")
        signal = rec.get("final_signal", "")

        if not ticker or not close_date or not signal:
            logger.warning("Skipping incomplete record: %s", rec)
            continue

        try:
            end_date = (
                datetime.strptime(close_date, "%Y-%m-%d") + timedelta(days=10)
            ).strftime("%Y-%m-%d")

            tk = yf.Ticker(ticker)
            hist = tk.history(start=close_date, end=end_date)

            if len(hist) < 2:
                # Next trading day not yet available (signal too recent)
                logger.info(
                    "Skipping %s %s — next-day data not yet available", ticker, close_date
                )
                continue

            signal_close = float(hist["Close"].iloc[0])
            next_close = float(hist["Close"].iloc[1])
            actual_return_pct = (next_close - signal_close) / signal_close * 100

            if signal in _BULLISH_SIGNALS:
                correct: bool | None = actual_return_pct > 0
            elif signal in _BEARISH_SIGNALS:
                correct = actual_return_pct < 0
            else:
                correct = None  # "uncertain" — excluded from accuracy calc

            evaluated.append(
                {
                    **rec,
                    "signal_close": round(signal_close, 2),
                    "next_close": round(next_close, 2),
                    "actual_next_day_pct": round(actual_return_pct, 2),
                    "correct": correct,
                }
            )
        except Exception as exc:
            logger.warning("Could not evaluate %s %s: %s", ticker, close_date, exc)

    _print_backtest_results(evaluated)


def _print_backtest_results(evaluated: list[dict]) -> None:
    """Print a formatted backtest accuracy report to stdout."""
    if not evaluated:
        print("No records could be evaluated (data may be too recent or history empty).")
        return

    directional = [r for r in evaluated if r["correct"] is not None]
    correct = [r for r in directional if r["correct"]]

    print()
    print("=" * 68)
    print("  SIGNAL HISTORY BACKTEST")
    print("=" * 68)
    print(f"Total evaluated records:  {len(evaluated)}")
    print(f"Directional signals:      {len(directional)}  (uncertain excluded)")

    if directional:
        accuracy = len(correct) / len(directional) * 100
        print(f"Correct predictions:      {len(correct)}")
        print(f"Accuracy:                 {accuracy:.1f}%")

    print()
    print(
        f"{'Date':<12} {'Ticker':<7} {'Signal':<22} {'Conf':>4}"
        f" {'Actual':>8}  {'OK?'}"
    )
    print("-" * 68)
    for r in evaluated:
        if r["correct"] is True:
            ok = "✓"
        elif r["correct"] is False:
            ok = "✗"
        else:
            ok = "—"
        print(
            f"{r['last_close_date']:<12}"
            f" {r['ticker']:<7}"
            f" {r['final_signal']:<22}"
            f" {r['confidence_0_100']:>4}"
            f" {r['actual_next_day_pct']:>+7.2f}%"
            f"  {ok}"
        )
    print("=" * 68)
    print()
    print(
        "NOTE: Next-day accuracy is a noisy metric. Use for trend "
        "observation only, not as performance guarantee."
    )


if __name__ == "__main__":
    run_backtest(Config())
