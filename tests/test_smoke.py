"""Minimal smoke tests for the signal pipeline components."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.utils import Config, DISCLAIMER
from src.news import Article, _deduplicate
from src.market import MarketData
from src.ai_analyze import (
    AnalysisResult,
    _parse_analysis,
    _rule_based_fallback,
)
from src.main import combine_signals
from src.news import _pre_filter_by_sentiment


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_defaults_load(self) -> None:
        """Config should load with defaults when no env vars set."""
        cfg = Config()
        assert cfg.topic  # Should have a default
        assert cfg.ticker
        assert cfg.data_dir.exists()

    def test_validate_missing_key(self) -> None:
        """Validation should catch missing OPENAI_API_KEY."""
        cfg = Config()
        cfg.openai_api_key = ""
        problems = cfg.validate()
        assert any("OPENAI_API_KEY" in p for p in problems)

    def test_validate_ok(self) -> None:
        """No problems when required fields are set."""
        cfg = Config()
        cfg.openai_api_key = "sk-test"
        assert cfg.validate() == []


# ---------------------------------------------------------------------------
# News deduplication
# ---------------------------------------------------------------------------

class TestNewsDedupe:
    def test_dedup_removes_duplicates(self) -> None:
        a1 = Article("Test Title", "Source1", "2024-01-01", "summary", "https://example.com/1")
        a2 = Article("Test Title", "Source2", "2024-01-02", "summary", "https://example.com/1")
        a3 = Article("Other Title", "Source1", "2024-01-01", "summary", "https://example.com/2")
        result = _deduplicate([a1, a2, a3])
        assert len(result) == 2

    def test_dedup_keeps_unique(self) -> None:
        articles = [
            Article(f"Title {i}", "Src", "2024-01-01", "", f"https://example.com/{i}")
            for i in range(5)
        ]
        result = _deduplicate(articles)
        assert len(result) == 5

    def test_dedup_skips_empty_title(self) -> None:
        a = Article("", "Src", "2024-01-01", "", "https://example.com/empty")
        result = _deduplicate([a])
        assert len(result) == 0


# ---------------------------------------------------------------------------
# AI JSON parsing
# ---------------------------------------------------------------------------

class TestAIParser:
    def test_parse_valid_json(self) -> None:
        raw = json.dumps({
            "news_sentiment": "positive",
            "key_drivers": ["strong earnings"],
            "risk_factors": ["macro headwinds"],
            "directional_bias": "likely_up",
            "confidence_0_100": 70,
            "one_paragraph_rationale": "Things look good.",
        })
        result = _parse_analysis(raw)
        assert result.news_sentiment == "positive"
        assert result.directional_bias == "likely_up"
        assert result.confidence_0_100 == 70

    def test_parse_with_markdown_fences(self) -> None:
        raw = '```json\n{"news_sentiment":"neutral","key_drivers":[],"risk_factors":[],"directional_bias":"uncertain","confidence_0_100":50,"one_paragraph_rationale":"test"}\n```'
        result = _parse_analysis(raw)
        assert result.news_sentiment == "neutral"

    def test_parse_invalid_json_raises(self) -> None:
        with pytest.raises((json.JSONDecodeError, Exception)):
            _parse_analysis("this is not json")

    def test_parse_clamps_confidence(self) -> None:
        raw = json.dumps({
            "news_sentiment": "mixed",
            "key_drivers": [],
            "risk_factors": [],
            "directional_bias": "uncertain",
            "confidence_0_100": 150,
            "one_paragraph_rationale": "test",
        })
        result = _parse_analysis(raw)
        assert result.confidence_0_100 == 100

    def test_parse_invalid_sentiment_defaults(self) -> None:
        raw = json.dumps({
            "news_sentiment": "INVALID",
            "key_drivers": [],
            "risk_factors": [],
            "directional_bias": "uncertain",
            "confidence_0_100": 50,
            "one_paragraph_rationale": "test",
        })
        result = _parse_analysis(raw)
        assert result.news_sentiment == "neutral"


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

class TestRuleBased:
    def _market(self, close_vs_sma7: str = "above", return_7d: float = 1.0) -> MarketData:
        return MarketData(
            ticker="TEST",
            last_close=100.0,
            last_close_date="2024-01-01",
            sma_7=99.0,
            sma_21=98.0,
            close_vs_sma7=close_vs_sma7,
            return_7d_pct=return_7d,
            prices_available=30,
        )

    def test_fallback_bullish(self) -> None:
        result = _rule_based_fallback([], self._market("above", 2.0))
        assert result.directional_bias == "likely_up"

    def test_fallback_bearish(self) -> None:
        result = _rule_based_fallback([], self._market("below", -2.0))
        assert result.directional_bias == "likely_down"

    def test_fallback_mixed(self) -> None:
        result = _rule_based_fallback([], self._market("above", -1.0))
        assert result.directional_bias == "uncertain"


# ---------------------------------------------------------------------------
# Signal combination (imported from main)
# ---------------------------------------------------------------------------

class TestCombineSignals:
    def _ai(self, bias: str) -> AnalysisResult:
        return AnalysisResult(
            news_sentiment="neutral",
            key_drivers=[],
            risk_factors=[],
            directional_bias=bias,
            confidence_0_100=50,
            one_paragraph_rationale="test",
        )

    def _market(self, vs_sma: str, ret: float) -> MarketData:
        return MarketData("TEST", 100.0, "2024-01-01", 99.0, 98.0, vs_sma, ret, 30)

    def test_all_bullish(self) -> None:
        assert combine_signals(self._ai("likely_up"), self._market("above", 1.0)) == "likely_up"

    def test_all_bearish(self) -> None:
        assert combine_signals(self._ai("likely_down"), self._market("below", -1.0)) == "likely_down"

    def test_conflicting_signals(self) -> None:
        # AI says up but market says below SMA
        assert combine_signals(self._ai("likely_up"), self._market("below", 1.0)) == "uncertain"

    def test_ai_uncertain(self) -> None:
        assert combine_signals(self._ai("uncertain"), self._market("above", 1.0)) == "uncertain"


# ---------------------------------------------------------------------------
# Disclaimer presence
# ---------------------------------------------------------------------------

class TestDisclaimer:
    def test_disclaimer_not_empty(self) -> None:
        assert len(DISCLAIMER) > 50
        assert "financial advice" in DISCLAIMER.lower() or "NOT" in DISCLAIMER


# ---------------------------------------------------------------------------
# Sentiment pre-filter (N1)
# ---------------------------------------------------------------------------

class TestSentimentPreFilter:
    def _article(self, title: str, summary: str = "") -> Article:
        return Article(title, "Src", "2024-01-01", summary, "https://example.com/1")

    def _mock_analyzer(self, score: float) -> MagicMock:
        analyzer = MagicMock()
        analyzer.polarity_scores.return_value = {"compound": score}
        return analyzer

    def test_strong_positive_kept(self) -> None:
        articles = [self._article("Stock surges on record earnings")]
        with patch("src.news.SentimentIntensityAnalyzer" if False else "vaderSentiment.vaderSentiment.SentimentIntensityAnalyzer") as mock_cls:
            mock_cls.return_value = self._mock_analyzer(0.8)
            with patch.dict("sys.modules", {"vaderSentiment": MagicMock(), "vaderSentiment.vaderSentiment": MagicMock(SentimentIntensityAnalyzer=mock_cls)}):
                result = _pre_filter_by_sentiment(articles, threshold=0.05)
        assert len(result) == 1

    def test_near_neutral_dropped(self) -> None:
        articles = [self._article("Company holds annual meeting")]
        with patch("vaderSentiment.vaderSentiment.SentimentIntensityAnalyzer") as mock_cls:
            mock_cls.return_value = self._mock_analyzer(0.02)
            with patch.dict("sys.modules", {"vaderSentiment": MagicMock(), "vaderSentiment.vaderSentiment": MagicMock(SentimentIntensityAnalyzer=mock_cls)}):
                result = _pre_filter_by_sentiment(articles, threshold=0.05)
        assert len(result) == 0

    def test_strong_negative_kept(self) -> None:
        articles = [self._article("Massive layoffs hit company amid losses")]
        with patch("vaderSentiment.vaderSentiment.SentimentIntensityAnalyzer") as mock_cls:
            mock_cls.return_value = self._mock_analyzer(-0.7)
            with patch.dict("sys.modules", {"vaderSentiment": MagicMock(), "vaderSentiment.vaderSentiment": MagicMock(SentimentIntensityAnalyzer=mock_cls)}):
                result = _pre_filter_by_sentiment(articles, threshold=0.05)
        assert len(result) == 1

    def test_empty_title_article_kept(self) -> None:
        articles = [Article("", "Src", "2024-01-01", "", "https://example.com/empty")]
        with patch("vaderSentiment.vaderSentiment.SentimentIntensityAnalyzer") as mock_cls:
            mock_cls.return_value = self._mock_analyzer(0.0)
            with patch.dict("sys.modules", {"vaderSentiment": MagicMock(), "vaderSentiment.vaderSentiment": MagicMock(SentimentIntensityAnalyzer=mock_cls)}):
                result = _pre_filter_by_sentiment(articles, threshold=0.05)
        assert len(result) == 1

    def test_import_error_returns_all(self) -> None:
        articles = [self._article("Some headline"), self._article("Another")]
        with patch.dict("sys.modules", {"vaderSentiment": None, "vaderSentiment.vaderSentiment": None}):
            result = _pre_filter_by_sentiment(articles, threshold=0.05)
        assert len(result) == 2

    def test_config_fields_default_off(self) -> None:
        cfg = Config()
        assert cfg.pre_filter_sentiment is False
        assert cfg.sentiment_filter_threshold == 0.05
