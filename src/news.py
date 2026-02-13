"""News ingestion: NewsAPI.org (if key present) with RSS fallback."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import feedparser
import requests

from src.utils import Config

logger = logging.getLogger("signal.news")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Article:
    title: str
    source: str
    published: str  # ISO-8601 string
    summary: str
    url: str

    def dedup_key(self) -> str:
        """Deterministic key for deduplication by URL + title."""
        raw = (self.url.strip().lower() + "|" + self.title.strip().lower())
        return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# NewsAPI
# ---------------------------------------------------------------------------

_NEWSAPI_URL = "https://newsapi.org/v2/everything"


def _fetch_newsapi(cfg: Config) -> list[Article]:
    """Fetch articles from NewsAPI.org."""
    from_dt = datetime.now(timezone.utc) - timedelta(hours=cfg.news_lookback_hours)
    params: dict[str, Any] = {
        "q": cfg.topic,
        "from": from_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 50,
        "apiKey": cfg.newsapi_key,
    }
    logger.info("Fetching news from NewsAPI for topic=%s", cfg.topic)
    resp = requests.get(_NEWSAPI_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "ok":
        logger.warning("NewsAPI returned status=%s: %s", data.get("status"), data.get("message"))
        return []

    articles: list[Article] = []
    for item in data.get("articles", []):
        articles.append(
            Article(
                title=item.get("title", "").strip(),
                source=item.get("source", {}).get("name", "unknown"),
                published=item.get("publishedAt", ""),
                summary=(item.get("description") or "")[:300],
                url=item.get("url", ""),
            )
        )
    logger.info("NewsAPI returned %d articles", len(articles))
    return articles


# ---------------------------------------------------------------------------
# RSS fallback
# ---------------------------------------------------------------------------

# Reputable RSS feeds that actually exist and serve RSS.
_RSS_FEEDS: list[tuple[str, str]] = [
    ("Google News", "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"),
    ("Bing News", "https://www.bing.com/news/search?q={query}&format=rss"),
    ("Yahoo Finance", "https://finance.yahoo.com/rss/headline?s={ticker}"),
]


def _fetch_rss(cfg: Config) -> list[Article]:
    """Fetch articles from RSS feeds (no API key required)."""
    articles: list[Article] = []
    for feed_name, url_template in _RSS_FEEDS:
        url = url_template.format(query=cfg.topic, ticker=cfg.ticker)
        logger.info("Fetching RSS: %s (%s)", feed_name, url)
        try:
            feed = feedparser.parse(url)
            if feed.bozo and not feed.entries:
                logger.warning("RSS feed %s returned no entries (bozo=%s)", feed_name, feed.bozo_exception)
                continue
            for entry in feed.entries[:20]:
                published = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
                    except Exception:
                        published = getattr(entry, "published", "")
                elif hasattr(entry, "published"):
                    published = entry.published

                articles.append(
                    Article(
                        title=getattr(entry, "title", "").strip(),
                        source=feed_name,
                        published=published,
                        summary=(getattr(entry, "summary", "") or "")[:300],
                        url=getattr(entry, "link", ""),
                    )
                )
        except Exception as exc:
            logger.warning("Failed to fetch RSS feed %s: %s", feed_name, exc)
    logger.info("RSS feeds returned %d articles total", len(articles))
    return articles


# ---------------------------------------------------------------------------
# Deduplication + filtering
# ---------------------------------------------------------------------------

def _deduplicate(articles: list[Article]) -> list[Article]:
    """Remove duplicate articles by URL+title hash."""
    seen: set[str] = set()
    unique: list[Article] = []
    for art in articles:
        key = art.dedup_key()
        if key not in seen and art.title:
            seen.add(key)
            unique.append(art)
    return unique


def _filter_by_lookback(articles: list[Article], hours: int) -> list[Article]:
    """Keep only articles within the lookback window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    filtered: list[Article] = []
    for art in articles:
        if not art.published:
            # Keep articles with unknown publish time (better to include)
            filtered.append(art)
            continue
        try:
            pub_dt = datetime.fromisoformat(art.published.replace("Z", "+00:00"))
            if pub_dt >= cutoff:
                filtered.append(art)
        except (ValueError, TypeError):
            filtered.append(art)  # Keep if we can't parse
    return filtered


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def fetch_news(cfg: Config) -> list[Article]:
    """Fetch, deduplicate, and return recent news articles."""
    articles: list[Article] = []

    if cfg.newsapi_key:
        try:
            articles = _fetch_newsapi(cfg)
        except Exception as exc:
            logger.warning("NewsAPI failed, falling back to RSS: %s", exc)
            articles = []

    if not articles:
        logger.info("Using RSS fallback for news ingestion")
        articles = _fetch_rss(cfg)

    articles = _deduplicate(articles)
    articles = _filter_by_lookback(articles, cfg.news_lookback_hours)

    # Sort by published time (newest first), unknowns at end
    articles.sort(key=lambda a: a.published or "0000", reverse=True)

    # Cache to data dir for debugging
    try:
        cache_path = cfg.data_dir / "last_news.json"
        cache_path.write_text(
            json.dumps([asdict(a) for a in articles], indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.debug("Could not write news cache: %s", exc)

    logger.info("Returning %d articles after dedup + filtering", len(articles))
    return articles
