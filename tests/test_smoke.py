"""Minimal smoke tests for the signal pipeline components."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import pandas as pd

from src.utils import Config, DISCLAIMER
from src.news import Article, _deduplicate
from src.market import MarketData, _compute_rsi, _compute_bollinger_bands, _compute_volume
from src.ai_analyze import (
    AnalysisResult,
    _parse_analysis,
    _rule_based_fallback,
    _apply_confidence_threshold,
)
from src.main import combine_signals
from src.news import _pre_filter_by_sentiment
from src.history import append_signal_record, load_history


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
            rsi_14=50.0,
            bb_upper=105.0,
            bb_middle=100.0,
            bb_lower=95.0,
            bb_position="inside",
            vol_10d_avg=1_000_000.0,
            vol_vs_avg="normal",
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
    def _ai(self, bias: str, confidence: int = 50) -> AnalysisResult:
        return AnalysisResult(
            news_sentiment="neutral",
            key_drivers=[],
            risk_factors=[],
            directional_bias=bias,
            confidence_0_100=confidence,
            one_paragraph_rationale="test",
        )

    def _market(self, vs_sma: str, ret: float) -> MarketData:
        return MarketData("TEST", 100.0, "2024-01-01", 99.0, 98.0, vs_sma, ret, 50.0, 105.0, 100.0, 95.0, "inside", 1_000_000.0, "normal", 30)

    def test_all_bullish(self) -> None:
        assert combine_signals(self._ai("likely_up"), self._market("above", 1.0)) == "likely_up"

    def test_all_bearish(self) -> None:
        assert combine_signals(self._ai("likely_down"), self._market("below", -1.0)) == "likely_down"

    def test_conflicting_signals(self) -> None:
        # AI says up but market says below SMA
        assert combine_signals(self._ai("likely_up"), self._market("below", 1.0)) == "uncertain"

    def test_ai_uncertain(self) -> None:
        assert combine_signals(self._ai("uncertain"), self._market("above", 1.0)) == "uncertain"

    def test_high_conviction_up(self) -> None:
        assert combine_signals(self._ai("likely_up", 70), self._market("above", 1.0)) == "high_conviction_up"

    def test_high_conviction_down(self) -> None:
        assert combine_signals(self._ai("likely_down", 75), self._market("below", -1.0)) == "high_conviction_down"

    def test_confidence_below_threshold_stays_likely_up(self) -> None:
        assert combine_signals(self._ai("likely_up", 69), self._market("above", 1.0)) == "likely_up"

    def test_confidence_at_threshold_is_high_conviction(self) -> None:
        assert combine_signals(self._ai("likely_up", 70), self._market("above", 1.0)) == "high_conviction_up"

    def test_high_conviction_requires_technical_confirmation(self) -> None:
        # High confidence but conflicting technicals → uncertain, not high_conviction
        assert combine_signals(self._ai("likely_up", 90), self._market("below", -1.0)) == "uncertain"


# ---------------------------------------------------------------------------
# Confidence threshold filter (A2)
# ---------------------------------------------------------------------------

class TestConfidenceThreshold:
    def _result(self, bias: str, confidence: int) -> AnalysisResult:
        return AnalysisResult(
            news_sentiment="positive",
            key_drivers=["test"],
            risk_factors=[],
            directional_bias=bias,
            confidence_0_100=confidence,
            one_paragraph_rationale="test",
        )

    def test_above_threshold_bias_unchanged(self) -> None:
        result = _apply_confidence_threshold(self._result("likely_up", 50), threshold=40)
        assert result.directional_bias == "likely_up"

    def test_below_threshold_overrides_to_uncertain(self) -> None:
        result = _apply_confidence_threshold(self._result("likely_up", 30), threshold=40)
        assert result.directional_bias == "uncertain"

    def test_at_threshold_bias_unchanged(self) -> None:
        # confidence == threshold → keep (only override when strictly less than)
        result = _apply_confidence_threshold(self._result("likely_down", 40), threshold=40)
        assert result.directional_bias == "likely_down"

    def test_override_preserves_other_fields(self) -> None:
        original = self._result("likely_up", 25)
        result = _apply_confidence_threshold(original, threshold=40)
        assert result.directional_bias == "uncertain"
        assert result.news_sentiment == "positive"
        assert result.confidence_0_100 == 25
        assert result.key_drivers == ["test"]

    def test_config_default_threshold_is_40(self) -> None:
        cfg = Config()
        assert cfg.confidence_threshold == 40

    def test_zero_confidence_overrides(self) -> None:
        result = _apply_confidence_threshold(self._result("likely_down", 0), threshold=40)
        assert result.directional_bias == "uncertain"


# ---------------------------------------------------------------------------
# Disclaimer presence
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Volume analysis (M3)
# ---------------------------------------------------------------------------

class TestVolumeAnalysis:
    def _series(self, volumes: list[float]) -> pd.Series:
        return pd.Series(volumes, dtype=float)

    def test_normal_volume_classified(self) -> None:
        # Today's volume equal to avg → "normal"
        vols = [1_000_000.0] * 10
        avg, label = _compute_volume(self._series(vols))
        assert label == "normal"
        assert avg == 1_000_000.0

    def test_high_volume_classified(self) -> None:
        # Today's volume > 1.5x avg
        vols = [1_000_000.0] * 9 + [2_000_000.0]
        _, label = _compute_volume(self._series(vols))
        assert label == "high"

    def test_low_volume_classified(self) -> None:
        # Today's volume < 0.75x avg
        vols = [1_000_000.0] * 9 + [500_000.0]
        _, label = _compute_volume(self._series(vols))
        assert label == "low"

    def test_uses_last_10_days(self) -> None:
        # 20 days of data; only last 10 should matter
        old_vols = [10_000_000.0] * 10   # old high volume ignored
        recent_vols = [1_000_000.0] * 9 + [2_000_000.0]
        avg, label = _compute_volume(self._series(old_vols + recent_vols))
        assert label == "high"
        assert avg == pytest.approx(1_100_000.0)

    def test_zero_volume_returns_normal(self) -> None:
        vols = [0.0] * 10
        avg, label = _compute_volume(self._series(vols))
        assert avg == 0.0
        assert label == "normal"

    def test_fewer_than_period_uses_available(self) -> None:
        vols = [1_000_000.0] * 5
        avg, label = _compute_volume(self._series(vols))
        assert avg == 1_000_000.0
        assert label == "normal"


# ---------------------------------------------------------------------------
# Bollinger Bands (M2)
# ---------------------------------------------------------------------------

class TestBollingerBands:
    def _series(self, prices: list[float]) -> pd.Series:
        return pd.Series(prices, dtype=float)

    def test_flat_prices_bands_straddle_mean(self) -> None:
        # All same price → std=0 → upper=lower=middle=price
        prices = [100.0] * 20
        upper, middle, lower, position = _compute_bollinger_bands(self._series(prices))
        assert upper == middle == lower == 100.0
        assert position == "inside"

    def test_close_above_upper_position(self) -> None:
        # Last price far above the band
        prices = [100.0] * 19 + [200.0]
        _, _, _, position = _compute_bollinger_bands(self._series(prices))
        assert position == "above_upper"

    def test_close_below_lower_position(self) -> None:
        # Last price far below the band
        prices = [100.0] * 19 + [0.0]
        _, _, _, position = _compute_bollinger_bands(self._series(prices))
        assert position == "below_lower"

    def test_close_inside_position(self) -> None:
        prices = [float(98 + i % 5) for i in range(20)]
        upper, middle, lower, position = _compute_bollinger_bands(self._series(prices))
        assert position == "inside"

    def test_upper_greater_than_lower(self) -> None:
        prices = [float(100 + (i % 3)) for i in range(25)]
        upper, middle, lower, _ = _compute_bollinger_bands(self._series(prices))
        assert upper >= middle >= lower

    def test_fewer_than_period_uses_available(self) -> None:
        # Only 10 points — should not raise, should use all 10
        prices = [float(100 + i) for i in range(10)]
        upper, middle, lower, _ = _compute_bollinger_bands(self._series(prices))
        assert upper > lower

    def test_middle_equals_window_mean(self) -> None:
        prices = [float(90 + i) for i in range(20)]
        _, middle, _, _ = _compute_bollinger_bands(self._series(prices))
        assert middle == round(sum(prices) / len(prices), 2)


# ---------------------------------------------------------------------------
# RSI indicator (M1)
# ---------------------------------------------------------------------------

class TestRSI:
    def _series(self, prices: list[float]) -> pd.Series:
        return pd.Series(prices, dtype=float)

    def test_insufficient_data_returns_50(self) -> None:
        # Fewer than period+1 (15) points → neutral fallback
        result = _compute_rsi(self._series([100.0] * 10))
        assert result == 50.0

    def test_all_gains_returns_100(self) -> None:
        # Monotonically increasing → no losses → RSI = 100
        prices = [float(100 + i) for i in range(15)]
        result = _compute_rsi(self._series(prices))
        assert result == 100.0

    def test_all_losses_returns_0(self) -> None:
        # Monotonically decreasing → no gains → RSI = 0
        prices = [float(114 - i) for i in range(15)]
        result = _compute_rsi(self._series(prices))
        assert result == 0.0

    def test_neutral_alternating_near_50(self) -> None:
        # Equal alternating gains and losses → RSI ≈ 50
        prices = [100.0 + (1.0 if i % 2 == 0 else -1.0) * (i % 2) for i in range(15)]
        prices = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0,
                  101.0, 100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0]
        result = _compute_rsi(self._series(prices))
        assert abs(result - 50.0) < 1.0

    def test_overbought_above_70(self) -> None:
        # 13 gains, 1 loss → strong uptrend → RSI > 70
        prices = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0,
                  108.0, 107.0, 108.0, 109.0, 110.0, 111.0, 112.0]
        result = _compute_rsi(self._series(prices))
        assert result > 70.0

    def test_oversold_below_30(self) -> None:
        # 1 gain, 13 losses → strong downtrend → RSI < 30
        prices = [112.0, 111.0, 110.0, 109.0, 108.0, 107.0, 106.0, 105.0,
                  104.0, 105.0, 104.0, 103.0, 102.0, 101.0, 100.0]
        result = _compute_rsi(self._series(prices))
        assert result < 30.0

    def test_result_in_valid_range(self) -> None:
        prices = [100.0, 102.0, 101.0, 103.0, 102.0, 104.0, 103.0,
                  105.0, 104.0, 106.0, 105.0, 107.0, 106.0, 108.0, 107.0]
        result = _compute_rsi(self._series(prices))
        assert 0.0 <= result <= 100.0


class TestDisclaimer:
    def test_disclaimer_not_empty(self) -> None:
        assert len(DISCLAIMER) > 50
        assert "financial advice" in DISCLAIMER.lower() or "NOT" in DISCLAIMER


# ---------------------------------------------------------------------------
# Signal history (S2)
# ---------------------------------------------------------------------------

class TestSignalHistory:
    def _market(self) -> MarketData:
        return MarketData(
            ticker="TEST",
            last_close=100.0,
            last_close_date="2024-01-15",
            sma_7=99.0,
            sma_21=98.0,
            close_vs_sma7="above",
            return_7d_pct=2.5,
            rsi_14=55.0,
            bb_upper=105.0,
            bb_middle=100.0,
            bb_lower=95.0,
            bb_position="inside",
            vol_10d_avg=1_000_000.0,
            vol_vs_avg="normal",
            prices_available=30,
        )

    def _ai(self) -> AnalysisResult:
        return AnalysisResult(
            news_sentiment="positive",
            key_drivers=["strong earnings"],
            risk_factors=["macro headwinds"],
            directional_bias="likely_up",
            confidence_0_100=75,
            one_paragraph_rationale="Test rationale.",
        )

    def test_append_creates_file(self, tmp_path) -> None:
        cfg = Config()
        cfg.data_dir = tmp_path
        append_signal_record(cfg, self._market(), self._ai(), "likely_up")
        assert (tmp_path / "signal_history.jsonl").exists()

    def test_append_writes_valid_json_with_expected_fields(self, tmp_path) -> None:
        cfg = Config()
        cfg.data_dir = tmp_path
        append_signal_record(cfg, self._market(), self._ai(), "likely_up")
        raw = (tmp_path / "signal_history.jsonl").read_text().strip()
        record = json.loads(raw)
        assert record["ticker"] == "TEST"
        assert record["final_signal"] == "likely_up"
        assert record["confidence_0_100"] == 75
        assert record["last_close"] == 100.0
        assert record["last_close_date"] == "2024-01-15"
        assert "run_at" in record

    def test_load_returns_empty_when_no_file(self, tmp_path) -> None:
        cfg = Config()
        cfg.data_dir = tmp_path
        assert load_history(cfg) == []

    def test_load_returns_all_appended_records(self, tmp_path) -> None:
        cfg = Config()
        cfg.data_dir = tmp_path
        append_signal_record(cfg, self._market(), self._ai(), "likely_up")
        append_signal_record(cfg, self._market(), self._ai(), "uncertain")
        records = load_history(cfg)
        assert len(records) == 2

    def test_append_preserves_signal_order(self, tmp_path) -> None:
        cfg = Config()
        cfg.data_dir = tmp_path
        append_signal_record(cfg, self._market(), self._ai(), "high_conviction_up")
        append_signal_record(cfg, self._market(), self._ai(), "likely_down")
        records = load_history(cfg)
        assert records[0]["final_signal"] == "high_conviction_up"
        assert records[1]["final_signal"] == "likely_down"

    def test_load_skips_malformed_lines(self, tmp_path) -> None:
        cfg = Config()
        cfg.data_dir = tmp_path
        hist_file = tmp_path / "signal_history.jsonl"
        hist_file.write_text('{"valid": true}\nNOT VALID JSON\n{"also": "valid"}\n')
        records = load_history(cfg)
        assert len(records) == 2


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
