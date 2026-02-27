"""Streamlit UI — Finance Signal Pro."""
from __future__ import annotations

import io
from datetime import date, timedelta, datetime

import pandas as pd
import streamlit as st

from src.utils import Config, DISCLAIMER
from src.main import run_pipeline
from src.history import load_history, append_signal_record

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Finance Signal Pro",
    page_icon="📈",
    layout="wide",
)

# ── Signal helpers ────────────────────────────────────────────────────────────
_SIGNAL_COLORS = {
    "high_conviction_up":   "#00c853",
    "likely_up":            "#4caf50",
    "uncertain":            "#ff9800",
    "likely_down":          "#f44336",
    "high_conviction_down": "#b71c1c",
}
_SIGNAL_LABELS = {
    "high_conviction_up":   "HIGH CONVICTION UP ▲▲",
    "likely_up":            "LIKELY UP ▲",
    "uncertain":            "UNCERTAIN —",
    "likely_down":          "LIKELY DOWN ▼",
    "high_conviction_down": "HIGH CONVICTION DOWN ▼▼",
}
_SIGNAL_LABELS_SHORT = {
    "high_conviction_up":   "HIGH CONVICTION UP",
    "likely_up":            "LIKELY UP",
    "uncertain":            "UNCERTAIN",
    "likely_down":          "LIKELY DOWN",
    "high_conviction_down": "HIGH CONVICTION DOWN",
}


# ── Session state init (runs once per browser session) ────────────────────────
def _init_session() -> None:
    _env = Config()
    defaults: dict = {
        "tickers":              ["MSFT"],
        "ticker_checked":       {"MSFT": True},
        "ai_provider":          _env.ai_provider,
        "openai_key":           _env.openai_api_key,
        "openai_model":         _env.openai_model,
        "claude_key":           _env.claude_api_key,
        "claude_model":         _env.claude_model,
        "google_key":           _env.google_api_key,
        "google_model":         _env.google_model,
        "perplexity_key":       _env.perplexity_api_key,
        "perplexity_model":     _env.perplexity_model,
        "confidence_threshold": _env.confidence_threshold,
        "newsapi_key":          _env.newsapi_key,
        "results":              {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_session()


# ── Config builder ────────────────────────────────────────────────────────────
def _build_cfg(ticker: str) -> Config:
    cfg = Config()
    cfg.ticker               = ticker
    cfg.topic                = ticker
    cfg.ai_provider          = st.session_state["ai_provider"]
    cfg.openai_api_key       = st.session_state["openai_key"]
    cfg.openai_model         = st.session_state["openai_model"]
    cfg.claude_api_key       = st.session_state["claude_key"]
    cfg.claude_model         = st.session_state["claude_model"]
    cfg.google_api_key       = st.session_state["google_key"]
    cfg.google_model         = st.session_state["google_model"]
    cfg.perplexity_api_key   = st.session_state["perplexity_key"]
    cfg.perplexity_model     = st.session_state["perplexity_model"]
    cfg.confidence_threshold = st.session_state["confidence_threshold"]
    cfg.newsapi_key          = st.session_state["newsapi_key"]
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="background:#16192a;padding:10px 14px;border-radius:6px;margin-bottom:10px;">'
        '<span style="color:#5aaeff;font-size:1.1em;font-weight:bold;letter-spacing:1px;">'
        "FINANCE SIGNAL PRO"
        "</span></div>",
        unsafe_allow_html=True,
    )

    # ── Settings ──────────────────────────────────────────────────────────────
    with st.expander("⚙ Settings", expanded=False):
        st.session_state["newsapi_key"] = st.text_input(
            "NewsAPI Key (optional)",
            value=st.session_state["newsapi_key"],
            type="password",
            help="Get a free key at newsapi.org for broader news coverage.",
        )
        st.session_state["confidence_threshold"] = st.slider(
            "Confidence Threshold",
            min_value=0,
            max_value=100,
            value=st.session_state["confidence_threshold"],
            help="AI signals below this confidence are overridden to UNCERTAIN.",
        )

    # ── AI Provider ───────────────────────────────────────────────────────────
    st.markdown("#### AI Provider")

    _PROVIDERS = {
        "OpenAI":        "openai",
        "Claude":        "claude",
        "Google Gemini": "google",
        "Perplexity":    "perplexity",
    }
    _PROV_LABELS = list(_PROVIDERS.keys())
    _PROV_VALS   = list(_PROVIDERS.values())

    _prov_idx = _PROV_VALS.index(st.session_state["ai_provider"]) \
                if st.session_state["ai_provider"] in _PROV_VALS else 0

    _selected_label = st.radio(
        "Provider", _PROV_LABELS, index=_prov_idx, label_visibility="collapsed"
    )
    st.session_state["ai_provider"] = _PROVIDERS[_selected_label]
    _prov = st.session_state["ai_provider"]

    if _prov == "openai":
        st.session_state["openai_key"] = st.text_input(
            "OpenAI API Key", value=st.session_state["openai_key"], type="password"
        )
        st.session_state["openai_model"] = st.text_input(
            "Model", value=st.session_state["openai_model"]
        )
    elif _prov == "claude":
        st.session_state["claude_key"] = st.text_input(
            "Claude API Key", value=st.session_state["claude_key"], type="password"
        )
        st.session_state["claude_model"] = st.text_input(
            "Model", value=st.session_state["claude_model"]
        )
    elif _prov == "google":
        st.session_state["google_key"] = st.text_input(
            "Google API Key", value=st.session_state["google_key"], type="password"
        )
        st.session_state["google_model"] = st.text_input(
            "Model", value=st.session_state["google_model"]
        )
    elif _prov == "perplexity":
        st.session_state["perplexity_key"] = st.text_input(
            "Perplexity API Key", value=st.session_state["perplexity_key"], type="password"
        )
        st.session_state["perplexity_model"] = st.text_input(
            "Model", value=st.session_state["perplexity_model"]
        )

    # ── Ticker List ───────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Ticker List")

    # Add input
    _add_col, _btn_col = st.columns([3, 1])
    with _add_col:
        _new_t = st.text_input(
            "ticker", key="new_ticker_input",
            label_visibility="collapsed",
            placeholder="e.g. AAPL",
        )
    with _btn_col:
        st.write("")  # vertical align
        if st.button("Add", use_container_width=True, key="btn_add_ticker"):
            _t = _new_t.strip().upper()
            if _t and _t not in st.session_state["tickers"]:
                st.session_state["tickers"].append(_t)
                st.session_state["ticker_checked"][_t] = True
                st.rerun()

    # Select all / none
    _sa, _sn = st.columns(2)
    with _sa:
        if st.button("✓ All", use_container_width=True):
            for _t in st.session_state["tickers"]:
                st.session_state["ticker_checked"][_t] = True
            st.rerun()
    with _sn:
        if st.button("○ None", use_container_width=True):
            for _t in st.session_state["tickers"]:
                st.session_state["ticker_checked"][_t] = False
            st.rerun()

    # Ticker rows: checkbox + remove button
    _to_remove: list[str] = []
    for _t in list(st.session_state["tickers"]):
        _chk_col, _rm_col = st.columns([5, 1])
        with _chk_col:
            _checked = st.checkbox(
                _t,
                value=st.session_state["ticker_checked"].get(_t, True),
                key=f"chk_{_t}",
            )
            st.session_state["ticker_checked"][_t] = _checked
        with _rm_col:
            if st.button("✕", key=f"rm_{_t}", help=f"Remove {_t}"):
                _to_remove.append(_t)

    if _to_remove:
        for _t in _to_remove:
            st.session_state["tickers"].remove(_t)
            st.session_state["ticker_checked"].pop(_t, None)
            st.session_state["results"].pop(_t, None)
        st.rerun()

    st.divider()
    _run_clicked = st.button(
        "▶  Run Selected Tickers",
        type="primary",
        use_container_width=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    '<div style="background:#161c2a;padding:12px 20px;border-radius:8px;margin-bottom:16px;">'
    '<span style="color:#5aaeff;font-size:1.35em;font-weight:bold;letter-spacing:1px;">'
    "📈 Finance Signal Pro"
    "</span></div>",
    unsafe_allow_html=True,
)

_tab_session, _tab_history = st.tabs(["  Current Session  ", "  Historical Analysis  "])

# ─────────────────────────────────────────────────────────────────────────────
# RUN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
if _run_clicked:
    _selected = [
        t for t in st.session_state["tickers"]
        if st.session_state["ticker_checked"].get(t, False)
    ]
    if not _selected:
        st.warning("No tickers selected. Check at least one ticker in the sidebar.")
    else:
        # Validate config once
        _problems = _build_cfg(_selected[0]).validate()
        if _problems:
            st.error("\n".join(_problems))
        else:
            _prog = st.progress(0, text="Starting analysis…")
            for _i, _ticker in enumerate(_selected):
                _prog.progress(
                    _i / len(_selected),
                    text=f"Analyzing {_ticker}… ({_i + 1}/{len(_selected)})",
                )
                _cfg = _build_cfg(_ticker)
                try:
                    _articles, _market, _ai, _signal, _report = run_pipeline(_cfg)
                    append_signal_record(_cfg, _market, _ai, _signal)
                    st.session_state["results"][_ticker] = {
                        "articles":     _articles,
                        "market":       _market,
                        "ai":           _ai,
                        "final_signal": _signal,
                        "report":       _report,
                        "error":        None,
                    }
                except Exception as _exc:
                    st.session_state["results"][_ticker] = {"error": str(_exc)}

            _prog.progress(1.0, text=f"Done — {len(_selected)} ticker(s) analyzed.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — CURRENT SESSION
# ─────────────────────────────────────────────────────────────────────────────
with _tab_session:
    _results = st.session_state["results"]

    if not _results:
        st.info(
            "Select tickers and configure your AI provider in the sidebar, "
            "then click **▶ Run Selected Tickers**."
        )
        st.warning(DISCLAIMER)
    else:
        # ── Summary grid ──────────────────────────────────────────────────────
        st.subheader("Results Summary")

        _summary_rows = []
        for _tk, _r in _results.items():
            if _r.get("error"):
                _summary_rows.append({
                    "Ticker":    _tk,
                    "Signal":    "ERROR",
                    "Conf":      "—",
                    "Sentiment": "—",
                    "Close":     "—",
                    "7d Return": "—",
                    "RSI-14":    "—",
                    "vs SMA-7":  "—",
                    "BB Position": "—",
                })
            else:
                _m  = _r["market"]
                _ai = _r["ai"]
                _summary_rows.append({
                    "Ticker":      _tk,
                    "Signal":      _SIGNAL_LABELS_SHORT.get(_r["final_signal"], _r["final_signal"].upper()),
                    "Conf":        _ai.confidence_0_100,
                    "Sentiment":   _ai.news_sentiment.upper(),
                    "Close":       f"${_m.last_close:,.2f}",
                    "7d Return":   f"{_m.return_7d_pct:+.2f}%",
                    "RSI-14":      f"{_m.rsi_14:.1f}",
                    "vs SMA-7":    _m.close_vs_sma7.upper(),
                    "BB Position": _m.bb_position.replace("_", " ").upper(),
                })

        _summary_df = pd.DataFrame(_summary_rows)
        st.dataframe(_summary_df, use_container_width=True, hide_index=True)

        st.divider()

        # ── Per-ticker detail ─────────────────────────────────────────────────
        st.subheader("Ticker Details")

        for _tk, _r in _results.items():
            with st.expander(f"**{_tk}**", expanded=len(_results) == 1):
                if _r.get("error"):
                    st.error(_r["error"])
                    continue

                _m      = _r["market"]
                _ai     = _r["ai"]
                _arts   = _r["articles"]
                _sig    = _r["final_signal"]
                _report = _r["report"]

                # Signal banner
                _color = _SIGNAL_COLORS.get(_sig, "#888")
                _label = _SIGNAL_LABELS.get(_sig, _sig.upper())
                st.markdown(
                    f'<div style="background:{_color};padding:16px 20px;border-radius:8px;'
                    f'text-align:center;margin-bottom:12px;">'
                    f'<h2 style="color:white;margin:0;font-size:1.8em;">{_label}</h2>'
                    f'<p style="color:rgba(255,255,255,0.85);margin:4px 0 0 0;">{_tk}</p>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

                # Key metrics
                _c1, _c2, _c3, _c4 = st.columns(4)
                _c1.metric(
                    "Last Close",
                    f"${_m.last_close:,.2f}",
                    delta=f"{_m.return_7d_pct:+.2f}% (7d)",
                )
                _c2.metric(
                    "RSI-14",
                    f"{_m.rsi_14:.1f}",
                    delta="overbought" if _m.rsi_14 > 70 else ("oversold" if _m.rsi_14 < 30 else None),
                )
                _c3.metric("AI Confidence", f"{_ai.confidence_0_100}/100")
                _c4.metric("vs SMA-7", _m.close_vs_sma7.upper())

                st.divider()

                # AI analysis
                st.markdown("**AI Analysis**")
                st.caption(
                    f"Sentiment: **{_ai.news_sentiment.upper()}**  ·  "
                    f"Bias: **{_ai.directional_bias}**  ·  "
                    f"Provider: **{st.session_state['ai_provider'].upper()}**"
                )

                _drv_col, _risk_col = st.columns(2)
                with _drv_col:
                    st.markdown("**Key Drivers**")
                    for _d in (_ai.key_drivers or ["(none)"]):
                        st.markdown(f"- {_d}")
                with _risk_col:
                    st.markdown("**Risk Factors**")
                    for _rf in (_ai.risk_factors or ["(none)"]):
                        st.markdown(f"- {_rf}")
                st.info(_ai.one_paragraph_rationale)

                # Market indicators
                with st.expander("Full Market Indicators"):
                    _ind_df = pd.DataFrame({
                        "Indicator": [
                            "Last Close", "SMA-7", "SMA-21", "Close vs SMA-7",
                            "7-Day Return", "RSI-14",
                            "BB Upper (20)", "BB Middle (20)", "BB Lower (20)", "BB Position",
                            "10-Day Avg Volume", "Volume vs Avg",
                        ],
                        "Value": [
                            f"${_m.last_close:,.2f}  ({_m.last_close_date})",
                            f"${_m.sma_7:,.2f}",
                            f"${_m.sma_21:,.2f}",
                            _m.close_vs_sma7.upper(),
                            f"{_m.return_7d_pct:+.2f}%",
                            f"{_m.rsi_14:.1f}" + (
                                "  ← overbought" if _m.rsi_14 > 70
                                else "  ← oversold" if _m.rsi_14 < 30 else ""
                            ),
                            f"${_m.bb_upper:,.2f}",
                            f"${_m.bb_middle:,.2f}",
                            f"${_m.bb_lower:,.2f}",
                            _m.bb_position.replace("_", " ").upper(),
                            f"{_m.vol_10d_avg:,.0f}",
                            _m.vol_vs_avg.upper(),
                        ],
                    })
                    st.table(_ind_df)

                # News articles
                with st.expander(f"News Articles ({len(_arts)})"):
                    if _arts:
                        for _art in _arts:
                            st.markdown(
                                f"**[{_art.title}]({_art.url})**  \n"
                                f"*{_art.source} — {_art.published}*"
                            )
                            if _art.summary:
                                _preview = _art.summary[:200]
                                if len(_art.summary) > 200:
                                    _preview += "…"
                                st.markdown(f"> {_preview}")
                            st.markdown("---")
                    else:
                        st.info("No articles fetched for this ticker.")

                # Full report
                with st.expander("Full Text Report"):
                    st.code(_report, language=None)

        st.warning(DISCLAIMER)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — HISTORICAL ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
with _tab_history:
    # Load all records
    try:
        _hist_cfg    = Config()
        _all_records = load_history(_hist_cfg)
    except Exception as _exc:
        st.error(f"Could not load history: {_exc}")
        _all_records = []

    if not _all_records:
        st.info(
            "No history yet. Run the pipeline on some tickers to start building a record."
        )
    else:
        # ── Filter bar ────────────────────────────────────────────────────────
        _f1, _f2, _f3, _f4 = st.columns([2, 2, 2, 1])

        _hist_tickers = sorted({r.get("ticker", "") for r in _all_records if r.get("ticker")})

        with _f1:
            _ticker_filter = st.selectbox(
                "Ticker", ["All Tickers"] + _hist_tickers, key="hist_ticker_filter"
            )
        with _f2:
            _from_date = st.date_input(
                "From", value=date.today() - timedelta(days=90), key="hist_from"
            )
        with _f3:
            _to_date = st.date_input(
                "To", value=date.today(), key="hist_to"
            )
        with _f4:
            st.write("")
            st.button("Refresh", use_container_width=True, key="hist_refresh")

        # ── Apply filters ─────────────────────────────────────────────────────
        _filtered: list[dict] = []
        for _rec in _all_records:
            _run_at = _rec.get("run_at", "")
            try:
                _dt = datetime.fromisoformat(_run_at).date()
            except Exception:
                _dt = date.today()

            if _ticker_filter != "All Tickers":
                if _rec.get("ticker", "").upper() != _ticker_filter.upper():
                    continue
            if _dt < _from_date or _dt > _to_date:
                continue
            _filtered.append(_rec)

        # ── Build DataFrame ───────────────────────────────────────────────────
        _hist_rows: list[dict] = []
        for _rec in _filtered:
            _run_at = _rec.get("run_at", "")
            try:
                _dt_str = datetime.fromisoformat(_run_at).strftime("%Y-%m-%d %H:%M")
            except Exception:
                _dt_str = _run_at[:16] if _run_at else "?"

            _close = _rec.get("last_close")
            _rsi   = _rec.get("rsi_14")
            _ret7  = _rec.get("return_7d_pct")
            _sig   = _rec.get("final_signal", "")
            _sma7  = _rec.get("close_vs_sma7", "")
            _sent  = _rec.get("news_sentiment", "")

            _hist_rows.append({
                "Date / Time (UTC)": _dt_str,
                "Ticker":    _rec.get("ticker", "?"),
                "Signal":    _SIGNAL_LABELS_SHORT.get(_sig, _sig.upper()),
                "Conf":      _rec.get("confidence_0_100", "?"),
                "Sentiment": _sent.upper() if _sent else "?",
                "Close ($)": f"${_close:.2f}" if isinstance(_close, (int, float)) else "?",
                "7d Ret %":  f"{_ret7:+.2f}%" if isinstance(_ret7, (int, float)) else "?",
                "vs SMA-7":  _sma7.upper() if _sma7 else "?",
                "RSI-14":    f"{_rsi:.1f}" if isinstance(_rsi, (int, float)) else "?",
            })

        if not _hist_rows:
            st.info("No records match the current filters.")
        else:
            _hist_df = pd.DataFrame(_hist_rows)

            # ── Summary stats ─────────────────────────────────────────────────
            _n_up   = sum(1 for r in _filtered if "up"        in r.get("final_signal", ""))
            _n_down = sum(1 for r in _filtered if "down"      in r.get("final_signal", ""))
            _n_unc  = sum(1 for r in _filtered if "uncertain" in r.get("final_signal", ""))

            _s1, _s2, _s3, _s4 = st.columns(4)
            _s1.metric("Total Records", len(_hist_rows))
            _s2.metric("Up Signals",       _n_up)
            _s3.metric("Down Signals",     _n_down)
            _s4.metric("Uncertain",        _n_unc)

            # ── CSV export ────────────────────────────────────────────────────
            _csv_buf = io.StringIO()
            _hist_df.to_csv(_csv_buf, index=False)
            st.download_button(
                "↓ Export CSV",
                data=_csv_buf.getvalue(),
                file_name=f"signal_history_{date.today()}.csv",
                mime="text/csv",
            )

            # ── Table ─────────────────────────────────────────────────────────
            st.dataframe(_hist_df, use_container_width=True, hide_index=True)
