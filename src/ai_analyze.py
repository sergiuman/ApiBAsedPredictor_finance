"""OpenAI-powered news + market analysis with strict JSON output."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from src.market import MarketData
from src.news import Article
from src.utils import Config

logger = logging.getLogger("signal.ai")

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


def _build_prompt(articles: list[Article], market: MarketData, cfg: Config) -> str:
    """Build the prompt for the OpenAI model."""
    headlines = []
    for a in articles[:30]:  # Limit to top 30 to stay within token limits
        headlines.append({
            "title": a.title,
            "source": a.source,
            "published": a.published,
            "url": a.url,
        })

    market_info = {
        "ticker": market.ticker,
        "last_close": market.last_close,
        "last_close_date": market.last_close_date,
        "sma_7": market.sma_7,
        "sma_21": market.sma_21,
        "close_vs_sma7": market.close_vs_sma7,
        "return_7d_pct": market.return_7d_pct,
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
    """Stricter prompt for retry after first parse failure."""
    base = _build_prompt(articles, market, cfg)
    return base + """

CRITICAL: Your previous response was not valid JSON. You MUST return ONLY a raw JSON object.
Do NOT wrap it in ```json``` or any markdown. Do NOT add any text before or after the JSON.
The response must start with { and end with }."""


def _parse_analysis(raw: str) -> AnalysisResult:
    """Parse and validate the AI response. Raises ValueError on failure."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        # Remove opening fence
        first_newline = text.index("\n") if "\n" in text else 3
        text = text[first_newline + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    data = json.loads(text)

    # Validate required fields
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


def _rule_based_fallback(articles: list[Article], market: MarketData) -> AnalysisResult:
    """Simple rule-based analysis when AI fails."""
    logger.warning("Using rule-based fallback (AI analysis failed)")

    # Simple heuristic: just use market momentum
    if market.close_vs_sma7 == "above" and market.return_7d_pct > 0:
        bias = "likely_up"
        sentiment = "positive"
    elif market.close_vs_sma7 == "below" and market.return_7d_pct < 0:
        bias = "likely_down"
        sentiment = "negative"
    else:
        bias = "uncertain"
        sentiment = "mixed"

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
# Public interface
# ---------------------------------------------------------------------------

def analyze(
    articles: list[Article],
    market: MarketData,
    cfg: Config,
) -> AnalysisResult:
    """Run AI analysis on news + market data. Falls back to rules on failure."""
    if not cfg.openai_api_key:
        logger.warning("No OPENAI_API_KEY set, using rule-based fallback")
        return _rule_based_fallback(articles, market)

    client = OpenAI(api_key=cfg.openai_api_key)

    # First attempt
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
            )
            raw = response.choices[0].message.content or ""
            logger.debug("Raw AI response: %s", raw[:500])
            result = _parse_analysis(raw)
            logger.info(
                "AI analysis: sentiment=%s, bias=%s, confidence=%d",
                result.news_sentiment, result.directional_bias, result.confidence_0_100,
            )
            return result

        except json.JSONDecodeError as exc:
            logger.warning("JSON parse failed (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                continue
        except Exception as exc:
            logger.error("OpenAI API error (attempt %d): %s", attempt + 1, exc)
            if attempt == 0:
                continue

    # Both attempts failed
    return _rule_based_fallback(articles, market)
