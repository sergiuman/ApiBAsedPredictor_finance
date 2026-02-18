"""Market data ingestion via yfinance with simple technical indicators."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from src.utils import Config

logger = logging.getLogger("signal.market")


def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    """Compute RSI using Wilder's smoothed moving average.

    Returns 50.0 if there are fewer than period+1 data points.
    Returns 100.0 when there are no losses (all gains).
    Returns 0.0 when there are no gains (all losses).
    """
    if len(close) < period + 1:
        logger.warning("Insufficient data for RSI (%d points); returning 50", len(close))
        return 50.0

    delta = close.diff().dropna()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    # Seed: simple mean over the first `period` changes
    avg_gain = float(gains.iloc[:period].mean())
    avg_loss = float(losses.iloc[:period].mean())

    # Wilder's smoothing for any data beyond the seed window
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + float(gains.iloc[i])) / period
        avg_loss = (avg_loss * (period - 1) + float(losses.iloc[i])) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _compute_bollinger_bands(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[float, float, float, str]:
    """Compute Bollinger Bands (20-day SMA ± 2 std deviations).

    Returns (bb_upper, bb_middle, bb_lower, bb_position).
    Uses all available data when fewer than period points exist.
    bb_position: "above_upper" | "inside" | "below_lower"
    """
    window = min(period, len(close))
    window_data = close.tail(window)

    middle = float(window_data.mean())
    std = float(window_data.std(ddof=1)) if window > 1 else 0.0

    upper = middle + num_std * std
    lower = middle - num_std * std

    last = float(close.iloc[-1])
    if last > upper:
        position = "above_upper"
    elif last < lower:
        position = "below_lower"
    else:
        position = "inside"

    return round(upper, 2), round(middle, 2), round(lower, 2), position


@dataclass
class MarketData:
    """Computed market indicators for a ticker."""

    ticker: str
    last_close: float
    last_close_date: str
    sma_7: float
    sma_21: float
    close_vs_sma7: str  # "above" or "below"
    return_7d_pct: float
    rsi_14: float        # 0-100; >70 overbought, <30 oversold
    bb_upper: float      # upper Bollinger Band (20-day SMA + 2σ)
    bb_middle: float     # middle Bollinger Band (20-day SMA)
    bb_lower: float      # lower Bollinger Band (20-day SMA - 2σ)
    bb_position: str     # "above_upper" | "inside" | "below_lower"
    prices_available: int  # number of trading days we got

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fetch_market_data(cfg: Config) -> MarketData:
    """Pull historical prices for TICKER and compute indicators.

    Raises ValueError on invalid ticker or insufficient data.
    """
    logger.info("Fetching market data for %s", cfg.ticker)
    tk = yf.Ticker(cfg.ticker)

    # Pull ~45 calendar days to ensure we have >=30 trading days
    hist = tk.history(period="3mo")

    if hist.empty:
        raise ValueError(
            f"No market data returned for ticker '{cfg.ticker}'. "
            "Check the ticker symbol is valid."
        )

    close = hist["Close"]
    if len(close) < 7:
        raise ValueError(
            f"Only {len(close)} trading days of data for '{cfg.ticker}'. "
            "Need at least 7 for indicators."
        )

    last_close = float(close.iloc[-1])
    last_close_date = str(close.index[-1].date())

    sma_7 = float(close.tail(7).mean())
    sma_21 = float(close.tail(min(21, len(close))).mean())

    close_vs_sma7 = "above" if last_close > sma_7 else "below"

    # 7-day return: (last - 7 ago) / 7 ago * 100
    price_7_ago = float(close.iloc[-8]) if len(close) >= 8 else float(close.iloc[0])
    return_7d_pct = round((last_close - price_7_ago) / price_7_ago * 100, 2)

    rsi_14 = _compute_rsi(close)
    bb_upper, bb_middle, bb_lower, bb_position = _compute_bollinger_bands(close)

    md = MarketData(
        ticker=cfg.ticker,
        last_close=round(last_close, 2),
        last_close_date=last_close_date,
        sma_7=round(sma_7, 2),
        sma_21=round(sma_21, 2),
        close_vs_sma7=close_vs_sma7,
        return_7d_pct=return_7d_pct,
        rsi_14=rsi_14,
        bb_upper=bb_upper,
        bb_middle=bb_middle,
        bb_lower=bb_lower,
        bb_position=bb_position,
        prices_available=len(close),
    )

    # Cache for debugging
    try:
        cache_path = cfg.data_dir / "last_market.json"
        cache_path.write_text(
            json.dumps(md.to_dict(), indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.debug("Could not write market cache: %s", exc)

    logger.info(
        "Market data: last_close=%.2f, sma7=%.2f, sma21=%.2f, 7d_return=%.2f%%, rsi14=%.2f",
        md.last_close, md.sma_7, md.sma_21, md.return_7d_pct, md.rsi_14,
    )
    return md
