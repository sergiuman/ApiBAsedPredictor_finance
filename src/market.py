"""Market data ingestion via yfinance with simple technical indicators."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yfinance as yf

from src.utils import Config

logger = logging.getLogger("signal.market")


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

    md = MarketData(
        ticker=cfg.ticker,
        last_close=round(last_close, 2),
        last_close_date=last_close_date,
        sma_7=round(sma_7, 2),
        sma_21=round(sma_21, 2),
        close_vs_sma7=close_vs_sma7,
        return_7d_pct=return_7d_pct,
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
        "Market data: last_close=%.2f, sma7=%.2f, sma21=%.2f, 7d_return=%.2f%%",
        md.last_close, md.sma_7, md.sma_21, md.return_7d_pct,
    )
    return md
