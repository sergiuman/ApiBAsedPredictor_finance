"""Streamlit local UI for News + Market Daily Signal."""

from __future__ import annotations

import streamlit as st

from src.utils import Config, DISCLAIMER
from src.main import run_pipeline

# ---------------------------------------------------------------------------
# Page config — MUST be the first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="News + Market Daily Signal",
    page_icon="📈",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "results" not in st.session_state:
    st.session_state["results"] = None

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Configuration")

    _default_cfg = Config()

    openai_key = st.text_input(
        "OpenAI API Key",
        value=_default_cfg.openai_api_key,
        type="password",
        help="Your OpenAI API key (sk-…)",
    )

    topic = st.text_input(
        "Company / Topic",
        value=_default_cfg.topic,
        help="The company or topic to search news for (e.g. Apple)",
    )

    ticker_raw = st.text_input(
        "Stock Ticker",
        value=_default_cfg.ticker,
        help="Stock ticker symbol (e.g. AAPL)",
    )
    ticker = ticker_raw.strip().upper()

    with st.expander("Advanced"):
        model = st.selectbox(
            "OpenAI Model",
            ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
            index=0,
        )
        confidence_threshold = st.slider(
            "Confidence Threshold",
            min_value=0,
            max_value=100,
            value=_default_cfg.confidence_threshold,
            help="Signals below this confidence are overridden to UNCERTAIN",
        )

    run_clicked = st.button("▶ Run Analysis", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Main area header (always visible)
# ---------------------------------------------------------------------------
st.title("📈 News + Market Daily Signal")

if not run_clicked and st.session_state["results"] is None:
    st.markdown(
        """
        Configure your analysis in the sidebar, then click **▶ Run Analysis**.

        This tool fetches recent news headlines and live market data, analyzes
        them with OpenAI, and produces a combined directional signal for the
        selected stock.
        """
    )
    st.warning(DISCLAIMER)

# ---------------------------------------------------------------------------
# Run pipeline when button clicked
# ---------------------------------------------------------------------------
if run_clicked:
    cfg = Config()
    cfg.openai_api_key = openai_key
    cfg.topic = topic
    cfg.ticker = ticker
    cfg.openai_model = model
    cfg.confidence_threshold = confidence_threshold

    problems = cfg.validate()
    if problems:
        st.session_state["results"] = {"error": "\n".join(problems)}
    else:
        with st.spinner(f"Analyzing {ticker} ({topic})…"):
            try:
                articles, market, ai_result, final_signal, report = run_pipeline(cfg)
                st.session_state["results"] = {
                    "articles": articles,
                    "market": market,
                    "ai": ai_result,
                    "final_signal": final_signal,
                    "report": report,
                    "topic": topic,
                    "ticker": ticker,
                    "error": None,
                }
            except ValueError as exc:
                st.session_state["results"] = {"error": str(exc)}
            except Exception as exc:
                st.session_state["results"] = {"error": f"Unexpected error: {exc}"}

# ---------------------------------------------------------------------------
# Display results
# ---------------------------------------------------------------------------
results = st.session_state.get("results")

if results:
    if results.get("error"):
        st.error(results["error"])
        st.warning(DISCLAIMER)
    else:
        market = results["market"]
        ai = results["ai"]
        articles = results["articles"]
        final_signal = results["final_signal"]
        report = results["report"]
        display_topic = results["topic"]
        display_ticker = results["ticker"]

        # --- Signal banner ---
        _signal_styles: dict[str, tuple[str, str]] = {
            "high_conviction_up":   ("#00c853", "HIGH CONVICTION UP ▲▲"),
            "likely_up":            ("#4caf50", "LIKELY UP ▲"),
            "uncertain":            ("#ff9800", "UNCERTAIN —"),
            "likely_down":          ("#f44336", "LIKELY DOWN ▼"),
            "high_conviction_down": ("#b71c1c", "HIGH CONVICTION DOWN ▼▼"),
        }
        color, label = _signal_styles.get(final_signal, ("#9e9e9e", final_signal.upper()))

        st.markdown(
            f'<div style="background-color:{color};padding:22px 24px;'
            f'border-radius:10px;text-align:center;margin-bottom:12px;">'
            f'<h1 style="color:white;margin:0;font-size:2.4em;letter-spacing:1px;">'
            f'{label}</h1>'
            f'<p style="color:rgba(255,255,255,0.85);margin:6px 0 0 0;font-size:1.1em;">'
            f'{display_ticker} — {display_topic}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # --- 4-column metrics ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Last Close", f"${market.last_close:,.2f}", delta=f"{market.return_7d_pct:+.2f}% (7d)")
        col2.metric(
            "RSI-14",
            f"{market.rsi_14:.1f}",
            delta="overbought" if market.rsi_14 > 70 else ("oversold" if market.rsi_14 < 30 else None),
        )
        col3.metric("AI Confidence", f"{ai.confidence_0_100}/100")
        col4.metric("7-Day Return", f"{market.return_7d_pct:+.2f}%")

        st.divider()

        # --- AI Analysis ---
        st.subheader("AI Analysis")
        st.caption(f"Sentiment: **{ai.news_sentiment.upper()}**  ·  Bias: **{ai.directional_bias}**")

        drv_col, risk_col = st.columns(2)
        with drv_col:
            st.markdown("**Key Drivers**")
            if ai.key_drivers:
                for d in ai.key_drivers:
                    st.markdown(f"- {d}")
            else:
                st.markdown("*(none)*")
        with risk_col:
            st.markdown("**Risk Factors**")
            if ai.risk_factors:
                for r in ai.risk_factors:
                    st.markdown(f"- {r}")
            else:
                st.markdown("*(none)*")

        st.info(ai.one_paragraph_rationale)

        st.divider()

        # --- Expanders ---
        with st.expander("Full Market Indicators"):
            indicators = {
                "Indicator": [
                    "Last Close",
                    "SMA-7",
                    "SMA-21",
                    "Close vs SMA-7",
                    "7-Day Return",
                    "RSI-14",
                    "BB Upper (20)",
                    "BB Middle (20)",
                    "BB Lower (20)",
                    "BB Position",
                    "10-Day Avg Volume",
                    "Volume vs Avg",
                ],
                "Value": [
                    f"${market.last_close:,.2f}  ({market.last_close_date})",
                    f"${market.sma_7:,.2f}",
                    f"${market.sma_21:,.2f}",
                    market.close_vs_sma7.upper(),
                    f"{market.return_7d_pct:+.2f}%",
                    f"{market.rsi_14:.1f}" + ("  ← overbought" if market.rsi_14 > 70 else "  ← oversold" if market.rsi_14 < 30 else ""),
                    f"${market.bb_upper:,.2f}",
                    f"${market.bb_middle:,.2f}",
                    f"${market.bb_lower:,.2f}",
                    market.bb_position.replace("_", " ").upper(),
                    f"{market.vol_10d_avg:,.0f}",
                    market.vol_vs_avg.upper(),
                ],
            }
            st.table(indicators)

        with st.expander(f"News Articles Used ({len(articles)})"):
            if articles:
                for article in articles:
                    st.markdown(
                        f"**[{article.title}]({article.url})**  \n"
                        f"*{article.source} — {article.published}*"
                    )
                    if article.summary:
                        preview = article.summary[:200]
                        if len(article.summary) > 200:
                            preview += "…"
                        st.markdown(f"> {preview}")
                    st.markdown("---")
            else:
                st.info("No articles were fetched for this analysis.")

        with st.expander("Full Text Report"):
            st.code(report, language=None)

        # --- Disclaimer always at bottom ---
        st.warning(DISCLAIMER)
