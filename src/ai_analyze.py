"""Multi-provider AI analysis: OpenAI, Claude, Google Gemini, Perplexity."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from typing import Any

from openai import OpenAI

from src.market import MarketData
from src.news import Article
from src.utils import Config

logger = logging.getLogger("signal.ai")

# ---------------------------------------------------------------------------
# Lazy optional imports for additional providers
# ---------------------------------------------------------------------------
try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False
    logger.debug("anthropic package not installed; Claude provider unavailable")

try:
    import google.generativeai as _genai
    _HAS_GOOGLE = True
except ImportError:
    _HAS_GOOGLE = False
    logger.debug("google-generativeai package not installed; Google provider unavailable")

# ---------------------------------------------------------------------------
# Analysis result model
# ---------------------------------------------------------------------------

VALID_SENTIMENTS = {"positive", "negative", "mixed", "neutral"}
VALID_BIASES = {"likely_up", "likely_down", "uncertain"}


@dataclass
class AnalysisResult:
    news_sentiment: str  # positive | negative | mixed | neutral
    key_drivers: list[str]
    risk_factors: list[str]
    directional_bias: str  # likely_up | likely_down | uncertain
    confidence_0_100: int
    one_paragraph_rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "news_sentiment": self.news_sentiment,
            "key_drivers": self.key_drivers,
            "risk_factors": self.risk_factors,
            "directional_bias": self.directional_bias,
            "confidence_0_100": self.confidence_0_100,
            "one_paragraph_rationale": self.one_paragraph_rationale,
        }


# ---------------------------------------------------------------------------
# Prompt builders (shared across all providers)
# ---------------------------------------------------------------------------

def _build_prompt(articles: list[Article], market: MarketData, cfg: Config) -> str:
    headlines = [
        {"title": a.title, "source": a.source, "published": a.published, "url": a.url}
        for a in articles[:30]
    ]
    market_info = {
        "ticker": market.ticker,
        "last_close": market.last_close,
        "last_close_date": market.last_close_date,
        "sma_7": market.sma_7,
        "sma_21": market.sma_21,
        "close_vs_sma7": market.close_vs_sma7,
        "return_7d_pct": market.return_7d_pct,
        "rsi_14": market.rsi_14,
        "bb_upper": market.bb_upper,
        "bb_middle": market.bb_middle,
        "bb_lower": market.bb_lower,
        "bb_position": market.bb_position,
        "vol_10d_avg": market.vol_10d_avg,
        "vol_vs_avg": market.vol_vs_avg,
    }
    return f"""You are a financial analyst assistant. Analyze the following news headlines and market data for {cfg.topic} ({cfg.ticker}).

NEWS HEADLINES:
{json.dumps(headlines, indent=2)}

MARKET INDICATORS:
{json.dumps(market_info, indent=2)}

Based on the above, produce a JSON object with EXACTLY this schema (no extra keys, no markdown fences):
{{
  "news_sentiment": "positive" | "negative" | "mixed" | "neutral",
  "key_drivers": ["string", ...],
  "risk_factors": ["string", ...],
  "directional_bias": "likely_up" | "likely_down" | "uncertain",
  "confidence_0_100": <integer 0-100>,
  "one_paragraph_rationale": "string"
}}

Rules:
- key_drivers: 1-5 bullet strings summarizing positive/negative catalysts
- risk_factors: 1-5 bullet strings summarizing risks
- confidence_0_100: your confidence in the directional_bias (0=no idea, 100=certain)
- one_paragraph_rationale: 2-4 sentences explaining your reasoning
- Return ONLY the JSON object. No markdown, no explanation outside the JSON."""


def _build_strict_retry_prompt(articles: list[Article], market: MarketData, cfg: Config) -> str:
    return _build_prompt(articles, market, cfg) + """

CRITICAL: Your previous response was not valid JSON. You MUST return ONLY a raw JSON object.
Do NOT wrap it in ```json``` or any markdown. Do NOT add any text before or after the JSON.
The response must start with { and end with }."""


# ---------------------------------------------------------------------------
# Response parser (shared)
# ---------------------------------------------------------------------------

def _parse_analysis(raw: str) -> AnalysisResult:
    """Parse and validate the AI response. Raises ValueError on failure."""
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.index("\n") if "\n" in text else 3
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    data = json.loads(text)

    sentiment = data.get("news_sentiment", "neutral")
    if sentiment not in VALID_SENTIMENTS:
        sentiment = "neutral"

    bias = data.get("directional_bias", "uncertain")
    if bias not in VALID_BIASES:
        bias = "uncertain"

    drivers = data.get("key_drivers", [])
    if not isinstance(drivers, list):
        drivers = [str(drivers)]
    drivers = [str(d) for d in drivers[:5]]

    risks = data.get("risk_factors", [])
    if not isinstance(risks, list):
        risks = [str(risks)]
    risks = [str(r) for r in risks[:5]]

    confidence = data.get("confidence_0_100", 50)
    if not isinstance(confidence, (int, float)):
        confidence = 50
    confidence = max(0, min(100, int(confidence)))

    rationale = str(data.get("one_paragraph_rationale", "No rationale provided."))

    return AnalysisResult(
        news_sentiment=sentiment,
        key_drivers=drivers,
        risk_factors=risks,
        directional_bias=bias,
        confidence_0_100=confidence,
        one_paragraph_rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

def _rule_based_fallback(articles: list[Article], market: MarketData) -> AnalysisResult:
    logger.warning("Using rule-based fallback (AI analysis failed)")
    if market.close_vs_sma7 == "above" and market.return_7d_pct > 0:
        bias, sentiment = "likely_up", "positive"
    elif market.close_vs_sma7 == "below" and market.return_7d_pct < 0:
        bias, sentiment = "likely_down", "negative"
    else:
        bias, sentiment = "uncertain", "mixed"

    return AnalysisResult(
        news_sentiment=sentiment,
        key_drivers=[f"7-day return: {market.return_7d_pct}%",
                     f"Price vs 7d SMA: {market.close_vs_sma7}"],
        risk_factors=["AI analysis unavailable - using basic trend only"],
        directional_bias=bias,
        confidence_0_100=25,
        one_paragraph_rationale=(
            f"Rule-based fallback: The stock is trading {market.close_vs_sma7} its "
            f"7-day SMA with a {market.return_7d_pct}% weekly return. Without AI "
            f"sentiment analysis of {len(articles)} news articles, confidence is low."
        ),
    )


# ---------------------------------------------------------------------------
# Confidence threshold filter
# ---------------------------------------------------------------------------

def _apply_confidence_threshold(result: AnalysisResult, threshold: int) -> AnalysisResult:
    if result.confidence_0_100 < threshold:
        logger.info(
            "Confidence %d below threshold %d; overriding directional_bias to 'uncertain'",
            result.confidence_0_100, threshold,
        )
        return replace(result, directional_bias="uncertain")
    return result


# ---------------------------------------------------------------------------
# Provider-specific backends
# ---------------------------------------------------------------------------

def _analyze_openai(articles: list[Article], market: MarketData, cfg: Config) -> AnalysisResult:
    """Analyze using OpenAI API."""
    if not cfg.openai_api_key:
        logger.warning("No OPENAI_API_KEY set, using rule-based fallback")
        return _rule_based_fallback(articles, market)

    client = OpenAI(api_key=cfg.openai_api_key)
    for attempt in range(2):
        prompt_fn = _build_prompt if attempt == 0 else _build_strict_retry_prompt
        prompt = prompt_fn(articles, market, cfg)
        try:
            logger.info("Calling OpenAI (%s), attempt %d", cfg.openai_model, attempt + 1)
            response = client.chat.completions.create(
                model=cfg.openai_model,
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            result = _parse_analysis(raw)
            result = _apply_confidence_threshold(result, cfg.confidence_threshold)
            logger.info("OpenAI: sentiment=%s, bias=%s, confidence=%d",
                        result.news_sentiment, result.directional_bias, result.confidence_0_100)
            return result
        except json.JSONDecodeError as exc:
            logger.warning("OpenAI JSON parse failed (attempt %d): %s", attempt + 1, exc)
        except Exception as exc:
            logger.error("OpenAI API error (attempt %d): %s", attempt + 1, exc)

    return _rule_based_fallback(articles, market)


def _analyze_claude(articles: list[Article], market: MarketData, cfg: Config) -> AnalysisResult:
    """Analyze using Anthropic Claude API."""
    if not _HAS_ANTHROPIC:
        logger.error("anthropic package not installed. Install with: pip install anthropic")
        return _rule_based_fallback(articles, market)
    if not cfg.claude_api_key:
        logger.warning("No CLAUDE_API_KEY set, using rule-based fallback")
        return _rule_based_fallback(articles, market)

    client = _anthropic.Anthropic(api_key=cfg.claude_api_key)  # type: ignore[union-attr]
    for attempt in range(2):
        prompt_fn = _build_prompt if attempt == 0 else _build_strict_retry_prompt
        prompt = prompt_fn(articles, market, cfg)
        try:
            logger.info("Calling Claude (%s), attempt %d", cfg.claude_model, attempt + 1)
            message = client.messages.create(
                model=cfg.claude_model,
                max_tokens=1024,
                system="You are a financial analyst. Respond only with valid JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text if message.content else ""
            result = _parse_analysis(raw)
            result = _apply_confidence_threshold(result, cfg.confidence_threshold)
            logger.info("Claude: sentiment=%s, bias=%s, confidence=%d",
                        result.news_sentiment, result.directional_bias, result.confidence_0_100)
            return result
        except json.JSONDecodeError as exc:
            logger.warning("Claude JSON parse failed (attempt %d): %s", attempt + 1, exc)
        except Exception as exc:
            logger.error("Claude API error (attempt %d): %s", attempt + 1, exc)

    return _rule_based_fallback(articles, market)


def _analyze_google(articles: list[Article], market: MarketData, cfg: Config) -> AnalysisResult:
    """Analyze using Google Gemini API."""
    if not _HAS_GOOGLE:
        logger.error("google-generativeai package not installed. Install with: pip install google-generativeai")
        return _rule_based_fallback(articles, market)
    if not cfg.google_api_key:
        logger.warning("No GOOGLE_API_KEY set, using rule-based fallback")
        return _rule_based_fallback(articles, market)

    _genai.configure(api_key=cfg.google_api_key)  # type: ignore[union-attr]
    model = _genai.GenerativeModel(  # type: ignore[union-attr]
        cfg.google_model,
        system_instruction="You are a financial analyst. Respond only with valid JSON.",
    )
    for attempt in range(2):
        prompt_fn = _build_prompt if attempt == 0 else _build_strict_retry_prompt
        prompt = prompt_fn(articles, market, cfg)
        try:
            logger.info("Calling Google Gemini (%s), attempt %d", cfg.google_model, attempt + 1)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.3, "max_output_tokens": 1024},
            )
            raw = response.text
            result = _parse_analysis(raw)
            result = _apply_confidence_threshold(result, cfg.confidence_threshold)
            logger.info("Google: sentiment=%s, bias=%s, confidence=%d",
                        result.news_sentiment, result.directional_bias, result.confidence_0_100)
            return result
        except json.JSONDecodeError as exc:
            logger.warning("Google JSON parse failed (attempt %d): %s", attempt + 1, exc)
        except Exception as exc:
            logger.error("Google API error (attempt %d): %s", attempt + 1, exc)

    return _rule_based_fallback(articles, market)


def _analyze_perplexity(articles: list[Article], market: MarketData, cfg: Config) -> AnalysisResult:
    """Analyze using Perplexity API (OpenAI-compatible endpoint)."""
    if not cfg.perplexity_api_key:
        logger.warning("No PERPLEXITY_API_KEY set, using rule-based fallback")
        return _rule_based_fallback(articles, market)

    client = OpenAI(
        api_key=cfg.perplexity_api_key,
        base_url="https://api.perplexity.ai",
    )
    for attempt in range(2):
        prompt_fn = _build_prompt if attempt == 0 else _build_strict_retry_prompt
        prompt = prompt_fn(articles, market, cfg)
        try:
            logger.info("Calling Perplexity (%s), attempt %d", cfg.perplexity_model, attempt + 1)
            response = client.chat.completions.create(
                model=cfg.perplexity_model,
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Respond only with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )
            raw = response.choices[0].message.content or ""
            result = _parse_analysis(raw)
            result = _apply_confidence_threshold(result, cfg.confidence_threshold)
            logger.info("Perplexity: sentiment=%s, bias=%s, confidence=%d",
                        result.news_sentiment, result.directional_bias, result.confidence_0_100)
            return result
        except json.JSONDecodeError as exc:
            logger.warning("Perplexity JSON parse failed (attempt %d): %s", attempt + 1, exc)
        except Exception as exc:
            logger.error("Perplexity API error (attempt %d): %s", attempt + 1, exc)

    return _rule_based_fallback(articles, market)


# ---------------------------------------------------------------------------
# Public interface — dispatches to the selected provider
# ---------------------------------------------------------------------------

def analyze(
    articles: list[Article],
    market: MarketData,
    cfg: Config,
) -> AnalysisResult:
    """Run AI analysis using the configured provider. Falls back to rules on failure."""
    provider = cfg.ai_provider.lower()
    logger.info("AI provider: %s", provider)

    if provider == "claude":
        return _analyze_claude(articles, market, cfg)
    elif provider == "google":
        return _analyze_google(articles, market, cfg)
    elif provider == "perplexity":
        return _analyze_perplexity(articles, market, cfg)
    else:
        # Default: OpenAI
        return _analyze_openai(articles, market, cfg)
