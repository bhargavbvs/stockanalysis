"""Daily morning brief (WhatsApp-friendly).

Sections
  1. Market mood     regime score with each component, index futures, VIX, yields, oil
  2. AI take         (optional, needs ANTHROPIC_API_KEY) what is moving markets today,
                     if/then scenarios for the coming catalysts, one lesson of the day.
                     Uses Claude with web search, so it reads today's news.
  3. Coming up       macro events and earnings for the next 7 days
  4. Your stocks     per holding: move, trend status, what the bot's rules say,
                     key levels, earnings date
  5. Watchlist       any live signals / setups
  6. Headlines       Yahoo Finance headlines for your holdings

Everything except section 2 is computed from market data, so the brief still
works (and costs nothing) without an API key.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from . import data, events as ev, scanner
from .config import Holding, Settings
from .report import DISCLAIMER
from .signals import (
    EARNINGS_BLOCK, EVENT_BLOCK, NO_DATA, REGIME_BLOCK, SECTOR_BLOCK, SETUP, SIGNAL, Signal,
)

log = logging.getLogger(__name__)

SNAPSHOT = [  # (symbol, label, kind)
    ("ES=F", "S&P fut", "pct"),
    ("NQ=F", "Nasdaq fut", "pct"),
    ("SPY", "SPY", "pct"),
    ("SOXX", "Chips (SOXX)", "pct"),
    ("^VIX", "VIX", "level"),
    ("^TNX", "10-yr", "yield"),
    ("BZ=F", "Brent", "price"),
    ("GC=F", "Gold", "price"),
    ("DX-Y.NYB", "Dollar idx", "level"),
]


@dataclass
class HoldingView:
    holding: Holding
    signal: Signal
    change_1d: Optional[float] = None
    news: list[dict] = field(default_factory=list)

    @property
    def pnl_pct(self) -> Optional[float]:
        h, px = self.holding, self.signal.price
        if h.cost and px:
            return (px / h.cost - 1) * 100
        return None


@dataclass
class BriefData:
    now: datetime
    ctx: scanner.Context
    snapshot: list[dict]
    upcoming: list[ev.Event]
    holdings: list[HoldingView]
    watch: list[Signal]

    @property
    def weekend(self) -> bool:
        return self.now.weekday() >= 5


# --------------------------------------------------------------------------- #
# Gathering
# --------------------------------------------------------------------------- #


def _snapshot(history: dict[str, pd.DataFrame]) -> list[dict]:
    rows = []
    for sym, label, kind in SNAPSHOT:
        df = history.get(sym)
        if df is None or len(df) < 2:
            continue
        last, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
        if kind == "yield" and last > 20:  # old-style ^TNX quote
            last, prev = last / 10, prev / 10
        rows.append({"symbol": sym, "label": label, "kind": kind, "last": last,
                     "change_pct": (last / prev - 1) * 100, "change_abs": last - prev,
                     "asof": df.index[-1].date().isoformat()})
    return rows


def gather(settings: Settings, now: Optional[datetime] = None) -> BriefData:
    tz = ZoneInfo(settings.brief_tz)
    now = (now or datetime.now(tz)).astimezone(tz)
    holdings = settings.portfolio or [Holding(s) for s in settings.watchlist[:8]]
    symbols = list(dict.fromkeys([h.symbol for h in holdings] + settings.watchlist))

    ctx = scanner.build_context(settings, symbols)
    extra = [s for s, _, _ in SNAPSHOT if s not in ctx.history]
    ctx.history.update(data.fetch_history(extra, period="3mo"))

    views = []
    for h in holdings:
        sig = scanner.analyze(h.symbol, ctx, settings, force_earnings=True)
        df = ctx.history.get(h.symbol)
        chg = None
        if df is not None and len(df) >= 2:
            chg = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[-2]) - 1) * 100
        views.append(HoldingView(h, sig, chg, data.fetch_news(h.symbol, limit=2)))

    held = {h.symbol for h in holdings}
    watch = [scanner.analyze(s, ctx, settings) for s in settings.watchlist if s not in held]
    watch = [w for w in watch if w.status in (SIGNAL, SETUP)]
    watch.sort(key=lambda w: (w.status != SIGNAL, -w.quality))

    # Earnings of holdings within 14 days are "coming up" too
    upcoming = ev.upcoming(ctx.events, ctx.today, days=14)
    for v in views:
        e = v.signal.earnings
        if e and e.status == "known" and 0 <= (e.next_date - ctx.today).days <= 14:
            upcoming.append(ev.Event(e.next_date, f"{v.holding.symbol} earnings", (v.holding.symbol,)))
    seen, uniq = set(), []
    for e in sorted(upcoming, key=lambda e: e.day):
        if (e.day, e.name) not in seen:
            seen.add((e.day, e.name))
            uniq.append(e)

    return BriefData(now, ctx, _snapshot(ctx.history), uniq, views, watch[:5])


# --------------------------------------------------------------------------- #
# Rendering (deterministic part)
# --------------------------------------------------------------------------- #

MODE_LINE = {
    "NORMAL": "normal size – the bot's rules are fully on",
    "CAUTION": "half size, CALLs only on HIGH-confidence setups",
    "DEFENSIVE": "no new CALLs – protect capital, PUT setups only",
}


def _fmt_snapshot(row: dict) -> str:
    k, last, chg = row["kind"], row["last"], row["change_pct"]
    if k == "yield":
        return f"{row['label']} {last:.2f}% ({row['change_abs'] * 100:+.0f} bp)"
    if k == "level":
        return f"{row['label']} {last:.1f} ({chg:+.1f}%)"
    if k == "price":
        return f"{row['label']} ${last:,.0f} ({chg:+.1f}%)"
    return f"{row['label']} {chg:+.1f}%"


def rules_say(sig: Signal) -> str:
    """One plain-English line: what the bot's own rules say about this stock."""
    v = sig.values
    e21, e200 = v.get("ema_21"), v.get("ema_200")
    if sig.status == SIGNAL:
        p = sig.plan
        return (f"valid {sig.direction} entry ({sig.confidence}); stop ${p.stop:,.2f}, "
                f"target ${p.target:,.2f}" if p else f"valid {sig.direction} entry")
    if sig.status == SETUP:
        need = "pullback to 21 EMA" if sig.direction == "CALL" else "rally to 21 EMA"
        tail = f" (${e21:,.2f})" if e21 else ""
        return f"{'uptrend' if sig.direction == 'CALL' else 'downtrend'} intact – wait for {need}{tail} and stochastic"
    if sig.status in (EARNINGS_BLOCK, EVENT_BLOCK, REGIME_BLOCK, SECTOR_BLOCK):
        return sig.headline.split("–", 1)[-1].strip() + " – no new entries"
    if sig.status == NO_DATA:
        return "not enough history"
    if e200 and sig.price and sig.price < e200:
        return "no uptrend and below the 200 EMA – rules don't support adding or new calls"
    return "no clear trend – rules say stand aside"


def render(b: BriefData, ai_text: Optional[str] = None) -> str:
    r = b.ctx.regime
    title = "Weekend brief" if b.weekend else "Morning brief"
    L = [f"☀️ *{title} – {b.now:%a %b %d}*", ""]

    if r.available:
        L.append(f"*Market mood: {r.mode} ({r.score}/5)* – {MODE_LINE[r.mode]}")
        for c in r.components:
            mark = "⚠️" if c.on else ("✅" if c.available else "➖")
            L.append(f"{mark} {c.detail}")
    else:
        L.append("*Market mood:* unavailable (market data download failed)")
    if b.snapshot:
        equity = [x for x in b.snapshot if x["kind"] == "pct"]
        macro = [x for x in b.snapshot if x["kind"] != "pct"]
        L.append("")
        if equity:
            L.append("📈 " + " · ".join(_fmt_snapshot(x) for x in equity))
        if macro:
            L.append("🌐 " + " · ".join(_fmt_snapshot(x) for x in macro))

    if ai_text:
        L += ["", ai_text.strip()]

    L += ["", "*Coming up (next 2 weeks)*"]
    if b.upcoming:
        for e in b.upcoming:
            days = (e.day - b.ctx.today).days
            when = "today" if days == 0 else "tomorrow" if days == 1 else f"{e.day:%a %b %d}"
            sector_note = f" (moves {e.scope[0]})" if ev.MARKET not in e.scope and len(e.scope) > 1 else ""
            L.append(f"• {when}: {e.name}{sector_note}")
    else:
        L.append("• no scheduled macro events")

    L += ["", "*Your stocks*" if any(v.holding.shares or v.holding.cost for v in b.holdings) else "*Stocks you follow*"]
    for v in b.holdings:
        s = v.signal
        head = f"*{v.holding.symbol}* ${s.price:,.2f}" if s.price else f"*{v.holding.symbol}*"
        bits = []
        if v.change_1d is not None:
            bits.append(f"{v.change_1d:+.1f}% d")
        if v.pnl_pct is not None:
            bits.append(f"{v.pnl_pct:+.0f}% vs cost")
        L.append(head + (f" ({', '.join(bits)})" if bits else ""))
        L.append(f"   ↳ {rules_say(s)}")
        extras = []
        if s.levels and s.levels.support:
            extras.append(f"support ${s.levels.support[0]:,.2f}")
        if s.levels and s.levels.resistance:
            extras.append(f"resistance ${s.levels.resistance[0]:,.2f}")
        if s.earnings and s.earnings.status == "known":
            extras.append(s.earnings.describe(b.ctx.today))
        if s.sector and s.sector.blocks_calls:
            extras.append(f"sector {s.sector.detail}")
        if extras:
            L.append("   " + " · ".join(extras))

    if b.watch:
        L += ["", "*Watchlist*"]
        for w in b.watch:
            icon = "🚨" if w.status == SIGNAL else "⏳"
            L.append(f"{icon} {w.symbol}: {w.headline}")

    heads = [(v.holding.symbol, n) for v in b.holdings for n in v.news[:1]]
    if heads and not ai_text:
        L += ["", "*Headlines*"]
        L += [f"• {sym}: {n['title']}" + (f" ({n['publisher']})" if n.get("publisher") else "") for sym, n in heads]

    L += ["", DISCLAIMER]
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# AI section (Claude + web search)
# --------------------------------------------------------------------------- #

AI_SYSTEM = """You write the "AI take" section of a daily WhatsApp market brief for one retail \
trader who buys US stock options and is learning how markets work. He runs a rule-based bot \
(Fibonacci EMA pullback entries, a market-regime score, an event veto). Your job: explain what \
is driving markets today, lay out scenarios for the upcoming catalysts, and teach one concept.

Rules:
- Use web search to find what is moving US stocks today (pre-market / overnight) and any news \
in the last 24 hours about the trader's holdings. Prefer Reuters, AP, CNBC, Bloomberg, WSJ, FT.
- Use only numbers from the provided facts or from your search results. Never invent figures.
- Do not tell him to buy or sell anything. Describe what the bot's rules say, the levels that \
matter, and what would change the picture. Phrase forecasts as possibilities, not certainties.
- Write in {language}. WhatsApp formatting only: *bold*, _italic_, "•" bullets. No markdown \
headers, tables or links. At most {max_chars} characters. Output only the section, no preamble.

Format exactly:
*What's moving markets*
• (2–3 bullets: the driver, and why it matters for stocks)
*Scenarios to watch*
• If <catalyst goes one way> → <likely market reaction> → <what the bot's rules would do>
• (2–3 scenarios tied to the upcoming events)
*Your stocks*
• (only holdings with news or a notable setup; skip this section if nothing stands out)
*Lesson of the day*
(2–3 sentences explaining one concept using today's data, e.g. why oil moves inflation \
expectations, what a VIX term-structure inversion means, why IV drops after earnings)"""


def facts_for_ai(b: BriefData) -> dict:
    r = b.ctx.regime
    return {
        "date": b.now.strftime("%A %B %d, %Y"),
        "weekend": b.weekend,
        "market_regime": {
            "mode": r.mode, "score": r.score,
            "components": [{"name": c.label, "on": c.on, "detail": c.detail} for c in r.components],
        },
        "market_snapshot": b.snapshot,
        "upcoming_events": [{"date": e.day.isoformat(), "name": e.name, "scope": e.scope_label} for e in b.upcoming],
        "holdings": [
            {
                "symbol": v.holding.symbol, "price": v.signal.price, "change_1d_pct": v.change_1d,
                "pnl_vs_cost_pct": v.pnl_pct, "bot_status": v.signal.headline, "rules_say": rules_say(v.signal),
                "support": v.signal.levels.support[:2] if v.signal.levels else [],
                "resistance": v.signal.levels.resistance[:2] if v.signal.levels else [],
                "earnings": v.signal.earnings.describe(b.ctx.today) if v.signal.earnings else None,
                "sector": v.signal.sector.detail if v.signal.sector else None,
                "yahoo_headlines": [n["title"] for n in v.news],
            }
            for v in b.holdings
        ],
        "watchlist_signals": [{"symbol": w.symbol, "status": w.headline} for w in b.watch],
    }


def ai_take(b: BriefData, settings: Settings, max_chars: int = 1800) -> Optional[str]:
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic package not installed – skipping AI section")
        return None

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=180)
    system = AI_SYSTEM.format(language=settings.brief_language, max_chars=max_chars)
    user = ("Facts from the bot (JSON):\n" + json.dumps(facts_for_ai(b), default=str, indent=1) +
            ("\n\nIt is the weekend: focus on the week ahead." if b.weekend else ""))
    messages = [{"role": "user", "content": user}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": settings.brief_max_searches}]
    try:
        for _ in range(4):  # pause_turn continuation
            resp = client.messages.create(model=settings.brief_model, max_tokens=2000, system=system,
                                          messages=messages, tools=tools)
            if resp.stop_reason != "pause_turn":
                break
            messages = [messages[0], {"role": "assistant", "content": resp.content}]
    except Exception as exc:
        log.error("AI brief failed: %s", exc)
        return None

    blocks = list(resp.content)
    last_tool = max((i for i, blk in enumerate(blocks) if blk.type != "text"), default=-1)
    text = "".join(blk.text for blk in blocks[last_tool + 1:] if blk.type == "text").strip()
    if not text:
        text = "".join(blk.text for blk in blocks if blk.type == "text").strip()
    return text[: max_chars + 400] or None


def build(settings: Settings, now: Optional[datetime] = None, use_ai: bool = True) -> str:
    b = gather(settings, now)
    return render(b, ai_take(b, settings) if use_ai else None)
