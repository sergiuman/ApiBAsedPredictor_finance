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

    # ── AI provider selection ────────────────────────────────────────────────
    # Supported values: openai | claude | google | perplexity
    ai_provider: str = field(
        default_factory=lambda: os.getenv("AI_PROVIDER", "openai").lower()
    )

    # OpenAI
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )

    # Claude (Anthropic)
    claude_api_key: str = field(
        default_factory=lambda: os.getenv("CLAUDE_API_KEY", "")
    )
    claude_model: str = field(
        default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-opus-4-6")
    )

    # Google Gemini
    google_api_key: str = field(
        default_factory=lambda: os.getenv("GOOGLE_API_KEY", "")
    )
    google_model: str = field(
        default_factory=lambda: os.getenv("GOOGLE_MODEL", "gemini-1.5-flash")
    )

    # Perplexity
    perplexity_api_key: str = field(
        default_factory=lambda: os.getenv("PERPLEXITY_API_KEY", "")
    )
    perplexity_model: str = field(
        default_factory=lambda: os.getenv("PERPLEXITY_MODEL", "sonar")
    )

    # ── Other settings ───────────────────────────────────────────────────────
    newsapi_key: str = field(default_factory=lambda: os.getenv("NEWSAPI_KEY", ""))
    confidence_threshold: int = field(
        default_factory=lambda: int(os.getenv("CONFIDENCE_THRESHOLD", "40"))
    )
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
        provider = self.ai_provider
        if provider == "openai" and not self.openai_api_key:
            problems.append("OPENAI_API_KEY is not set.")
        elif provider == "claude" and not self.claude_api_key:
            problems.append("CLAUDE_API_KEY is not set.")
        elif provider == "google" and not self.google_api_key:
            problems.append("GOOGLE_API_KEY is not set.")
        elif provider == "perplexity" and not self.perplexity_api_key:
            problems.append("PERPLEXITY_API_KEY is not set.")
        # Fallback: if provider is unknown or openai is default, check openai key
        elif provider not in {"openai", "claude", "google", "perplexity"} and not self.openai_api_key:
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
