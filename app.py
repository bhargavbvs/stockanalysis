"""Streamlit dashboard (optional).

    pip install -r requirements-app.txt
    streamlit run app.py

Uses the same engine as the alerts, so what you see here is what the bot sends.
The old version also tried to start the Telegram bot in a background thread;
that can't work (python-telegram-bot needs the main thread) and is gone – run
`python -m stockbot.bot` separately if you want the bot.
"""

import plotly.graph_objects as go
import streamlit as st

from stockbot import config, indicators, scanner
from stockbot.signals import SIGNAL

st.set_page_config(page_title="Stock Trend Analyzer", page_icon="📈", layout="wide")
settings = config.load()


@st.cache_data(ttl=600, show_spinner=False)
def analyze(symbol: str):
    ctx = scanner.build_context(settings, [symbol])
    sig = scanner.analyze(symbol, ctx, settings, force_earnings=True)
    df = ctx.history.get(symbol)
    return sig, (indicators.compute(df).tail(180) if df is not None else None)


with st.sidebar:
    symbol = st.text_input("Ticker", value="NVDA").strip().upper()
    st.caption("Educational only – not financial advice.")

if symbol:
    with st.spinner(f"Analyzing {symbol}…"):
        sig, ind = analyze(symbol)

    r = sig.regime
    if r is not None and r.available:
        st.info(f"**Market mood: {r.mode} ({r.score}/5)** — " + "; ".join(c.detail for c in r.components))

    box = st.success if sig.status == SIGNAL else st.warning
    box(f"### {sig.symbol}: {sig.headline}")
    if sig.price:
        c1, c2, c3, c4 = st.columns(4)
        v = sig.values
        c1.metric("Price", f"${sig.price:,.2f}")
        c2.metric("RSI 14", f"{v['rsi']:.1f}" if v.get("rsi") else "n/a")
        c3.metric("Stochastic %K", f"{v['stoch_k']:.1f}" if v.get("stoch_k") else "n/a")
        c4.metric("ADX 13", f"{v['adx']:.1f}" if v.get("adx") else "n/a")

    if ind is not None:
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=ind.index, open=ind.Open, high=ind.High, low=ind.Low, close=ind.Close,
                                     name=symbol))
        for span in (8, 21, 34, 55, 89):
            fig.add_trace(go.Scatter(x=ind.index, y=ind[f"ema_{span}"], name=f"EMA {span}", line=dict(width=1)))
        if sig.plan:
            fig.add_hline(y=sig.plan.stop, line_dash="dot", line_color="red", annotation_text="stop")
            fig.add_hline(y=sig.plan.target, line_dash="dot", line_color="green", annotation_text="target")
        fig.update_layout(height=520, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)

    for c in sig.checks:
        (st.success if c.passed else st.error)(f"**{c.name}** — {c.detail}" if c.detail else c.name)

    if sig.plan:
        p = sig.plan
        st.subheader("Plan (underlying)")
        st.markdown(
            f"- Entry ≈ **${p.entry:,.2f}**\n"
            f"- Stop **${p.stop:,.2f}** ({p.stop_pct:+.1f}%, {p.stop_basis})\n"
            f"- Target {p.target_r:g}R **${p.target:,.2f}**\n"
            f"- Time stop {p.max_hold_bars} trading days"
            + (f"\n- Size {p.shares} shares (≈ ${p.risk_dollars:,.0f} at risk)" if p.shares is not None else "")
        )
        for n in p.notes:
            st.caption(f"⚠️ {n}")
    for w in sig.warnings:
        st.caption(f"⚠️ {w}")
