"""Configuration loading, logging setup, and shared helpers."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env from project root (two levels up from this file, or cwd)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"
load_dotenv(_ENV_PATH)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger("signal")


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------
@dataclass
class Config:
    """All runtime configuration, loaded from environment variables."""

    topic: str = field(default_factory=lambda: os.getenv("TOPIC", "Microsoft"))
    ticker: str = field(default_factory=lambda: os.getenv("TICKER", "MSFT"))
    news_lookback_hours: int = field(
        default_factory=lambda: int(os.getenv("NEWS_LOOKBACK_HOURS", "24"))
    )
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )
    newsapi_key: str = field(default_factory=lambda: os.getenv("NEWSAPI_KEY", ""))
    pre_filter_sentiment: bool = field(
        default_factory=lambda: os.getenv("PRE_FILTER_SENTIMENT", "false").lower() == "true"
    )
    sentiment_filter_threshold: float = field(
        default_factory=lambda: float(os.getenv("SENTIMENT_FILTER_THRESHOLD", "0.05"))
    )
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )
    telegram_chat_id: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", "")
    )

    # Derived
    data_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.data_dir = _PROJECT_ROOT / "data"
        self.data_dir.mkdir(exist_ok=True)

    def validate(self) -> list[str]:
        """Return a list of problems (empty = OK)."""
        problems: list[str] = []
        if not self.openai_api_key:
            problems.append("OPENAI_API_KEY is not set.")
        if not self.ticker:
            problems.append("TICKER is not set.")
        if not self.topic:
            problems.append("TOPIC is not set.")
        return problems


# ---------------------------------------------------------------------------
# Disclaimer
# ---------------------------------------------------------------------------
DISCLAIMER = (
    "DISCLAIMER: This output is for informational and educational purposes only. "
    "It does NOT constitute financial advice, investment recommendation, or a "
    "solicitation to buy or sell any security. Always do your own research and "
    "consult a qualified financial advisor before making investment decisions. "
    "Past performance is not indicative of future results."
)
