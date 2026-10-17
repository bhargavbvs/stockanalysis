"""Daily brief, sent as two WhatsApp messages (BRIEF_SPLIT=false sends one).

Message 1 – Market news
  Market mood (regime score + each component), futures / VIX / yields / oil,
  the AI section (what moved markets, Washington and the Fed, what the pros
  say, scenarios, lesson of the day), and the next two weeks of events.

Message 2 – Your stocks
  Portfolio totals, then the largest BRIEF_DEEP_STOCKS holdings in depth:
  move, P&L, what the bot's rules say, revenue growth / margin / P/E, analyst
  ratings and targets, levels, earnings. Leveraged ETFs (SNXX = 2x SanDisk)
  are explained through the company behind them, with the decay math: how the
  fund did against its stock, and what the stock must do to get the fund back
  to your cost. Then one line per remaining holding, your option positions
  (value, days left, time decay per day, the two break-even prices), the
  watchlist, and per-stock news (AI) or Yahoo headlines.

Everything except the AI parts is computed from market data, so the brief
still works (and costs nothing) without an API key.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from . import data, events as ev, leverage as lev, options as opt, scanner
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


def money(x: Optional[float], sign: bool = False) -> str:
    if x is None:
        return "–"
    s = "-" if x < 0 else ("+" if sign else "")
    a = abs(x)
    if a >= 1e6:
        return f"{s}${a / 1e6:.1f}M"
    if a >= 1e4:
        return f"{s}${a / 1e3:.1f}K"
    return f"{s}${a:,.0f}"


@dataclass
class HoldingView:
    holding: Holding
    signal: Signal
    change_1d: Optional[float] = None
    news: list[dict] = field(default_factory=list)
    prev_close: Optional[float] = None
    last: Optional[float] = None  # last close, even when the rules have too little history
    fund: Optional[lev.LeveragedETF] = None  # set when the holding is a leveraged ETF
    lev: Optional[lev.LeverageView] = None
    fundamentals: Optional[data.Fundamentals] = None
    deep: bool = False

    @property
    def company(self) -> str:
        return self.fund.underlying if self.fund else self.holding.symbol

    @property
    def price(self) -> Optional[float]:
        return self.signal.price or self.last

    @property
    def pnl_pct(self) -> Optional[float]:
        h, px = self.holding, self.price
        if h.cost and px:
            return (px / h.cost - 1) * 100
        return None

    @property
    def value(self) -> Optional[float]:
        h, px = self.holding, self.price
        return h.shares * px if h.shares and px else None

    @property
    def basis(self) -> Optional[float]:
        h = self.holding
        return h.shares * h.cost if h.shares and h.cost else None

    @property
    def day_pnl(self) -> Optional[float]:
        h, px = self.holding, self.price
        return h.shares * (px - self.prev_close) if h.shares and px and self.prev_close else None

    @property
    def company_price(self) -> Optional[float]:
        if self.fund:
            return self.lev.under_price if self.lev else None
        return self.price


@dataclass
class BriefData:
    now: datetime
    ctx: scanner.Context
    snapshot: list[dict]
    upcoming: list[ev.Event]
    holdings: list[HoldingView]
    watch: list[Signal]
    options: list[opt.OptionView] = field(default_factory=list)

    @property
    def weekend(self) -> bool:
        return self.now.weekday() >= 5


@dataclass
class AIText:
    news: Optional[str] = None
    stocks: Optional[str] = None


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


def _close(history: dict[str, pd.DataFrame], sym: str) -> Optional[pd.Series]:
    df = history.get(sym)
    return None if df is None or df.empty else df["Close"]


def gather(settings: Settings, now: Optional[datetime] = None) -> BriefData:
    tz = ZoneInfo(settings.brief_tz)
    now = (now or datetime.now(tz)).astimezone(tz)
    holdings = settings.portfolio or [Holding(s) for s in settings.watchlist[:8]]
    symbols = list(dict.fromkeys([h.symbol for h in holdings] + settings.watchlist))

    ctx = scanner.build_context(settings, symbols)
    funds = {h.symbol: settings.leveraged[h.symbol] for h in holdings if h.symbol in settings.leveraged}
    extra = [s for s, _, _ in SNAPSHOT] + [f.underlying for f in funds.values()] + [o.underlying for o in settings.options]
    extra = [s for s in dict.fromkeys(extra) if s not in ctx.history]
    fetched = data.fetch_history(extra, period="6mo")
    if settings.confirm_on_close and scanner.market_is_open():
        # build_context dropped today's unfinished bar; do the same so a fund and its stock line up
        under = {f.underlying for f in funds.values()} | {o.underlying for o in settings.options}
        fetched.update(scanner._drop_partial({k: v for k, v in fetched.items() if k in under}, ctx.today))
    ctx.history.update(fetched)

    views = []
    for h in holdings:
        sig = scanner.analyze(h.symbol, ctx, settings, force_earnings=True)
        close = _close(ctx.history, h.symbol)
        chg = prev = last = None
        if close is not None and len(close):
            last = float(close.iloc[-1])
        if close is not None and len(close) >= 2:
            prev = float(close.iloc[-2])
            chg = (last / prev - 1) * 100
        v = HoldingView(h, sig, chg, prev_close=prev, last=last, fund=funds.get(h.symbol))
        if v.fund:
            v.lev = lev.view(v.fund, close, _close(ctx.history, v.fund.underlying), h.cost)
        views.append(v)

    if any(v.value for v in views):
        views.sort(key=lambda v: -(v.value or 0))
    for v in views[: max(settings.brief_deep_stocks, 0)]:
        v.deep = True
        v.fundamentals = data.fetch_fundamentals(v.company, ctx.today)
    for v in views:
        v.news = data.fetch_news(v.company, limit=2) if v.deep else []

    options = []
    for o in settings.options:
        spot = _close(ctx.history, o.underlying)
        e = data.get_next_earnings(o.underlying, ctx.today)
        options.append(opt.build_view(o, ctx.today, None if spot is None else float(spot.iloc[-1]),
                                      data.fetch_option_quote(o.underlying, o.expiry, o.strike, o.right),
                                      e.next_date if e.status == "known" else None))

    held = {h.symbol for h in holdings}
    watch = [scanner.analyze(s, ctx, settings) for s in settings.watchlist if s not in held]
    watch = [w for w in watch if w.status in (SIGNAL, SETUP)]
    watch.sort(key=lambda w: (w.status != SIGNAL, -w.quality))

    # Earnings of holdings (and of the companies behind leveraged ETFs) within 14 days
    upcoming = ev.upcoming(ctx.events, ctx.today, days=14)
    for v in views:
        e = v.signal.earnings
        if e and e.status == "known" and 0 <= (e.next_date - ctx.today).days <= 14:
            name = f"{v.company} earnings" + (f" (your {v.holding.symbol})" if v.fund else "")
            upcoming.append(ev.Event(e.next_date, name, (v.holding.symbol,)))
    for o in options:
        d = o.earnings_before_expiry
        if d and 0 <= (d - ctx.today).days <= 14:
            upcoming.append(ev.Event(d, f"{o.holding.underlying} earnings", (o.holding.underlying,)))
    seen, uniq = set(), []
    for e in sorted(upcoming, key=lambda e: e.day):
        key = (e.day, e.name.split(" (")[0])
        if key not in seen:
            seen.add(key)
            uniq.append(e)

    return BriefData(now, ctx, _snapshot(ctx.history), uniq, views, watch[:5], options)


# --------------------------------------------------------------------------- #
# Rendering (deterministic part)
# --------------------------------------------------------------------------- #

MODE_LINE = {
    "NORMAL": "normal size – the bot's rules are fully on",
    "CAUTION": "half size, CALLs only on HIGH-confidence setups",
    "DEFENSIVE": "no new CALLs pass the rules; only PUT setups qualify",
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
        tail = f" (${e21:,.2f})" if e21 else ""
        if sig.direction == "CALL":
            return f"uptrend intact – a CALL entry needs a pullback to the 21 EMA{tail} and the stochastic to reset"
        return f"downtrend intact – no CALLs; a PUT entry needs a rally to the 21 EMA{tail} and the stochastic to reset"
    if sig.status in (EARNINGS_BLOCK, EVENT_BLOCK, REGIME_BLOCK, SECTOR_BLOCK):
        return sig.headline.split("–", 1)[-1].strip() + " – no new entries"
    if sig.status == NO_DATA:
        return "not enough history"
    if e200 and sig.price and sig.price < e200:
        return "no uptrend and below the 200 EMA – rules don't support adding or new calls"
    return "no clear trend – rules say stand aside"


SHORT = {EARNINGS_BLOCK: "earnings blackout", EVENT_BLOCK: "macro-event veto", REGIME_BLOCK: "market blocks CALLs",
         SECTOR_BLOCK: "sector blocks CALLs", NO_DATA: "too little history"}


def rules_short(sig: Signal) -> str:
    if sig.status == SIGNAL:
        return f"{sig.direction} signal ({sig.confidence})"
    if sig.status == SETUP:
        return "uptrend" if sig.direction == "CALL" else "downtrend"
    if sig.status in SHORT:
        return SHORT[sig.status]
    e200 = sig.values.get("ema_200")
    if e200 and sig.price and sig.price < e200:
        return "no trend, below 200 EMA"
    return "no clear trend"


def _date_line(b: BriefData) -> str:
    return f"{b.now:%a %b %d}"


def render_news(b: BriefData, ai_news: Optional[str] = None) -> str:
    r = b.ctx.regime
    title = "Weekend market news" if b.weekend else "Market news"
    L = [f"📰 *{title} – {_date_line(b)}*", ""]
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

    if ai_news:
        L += ["", ai_news.strip()]

    L += ["", "*Coming up (next 2 weeks)*"]
    runs_out = ev.calendar_runs_out(b.ctx.events, b.ctx.today)
    if runs_out is not None:
        L.append(f"⚠️ events.yaml has no market events after {runs_out:%b %d} – add the next CPI/jobs/FOMC dates")
    if b.upcoming:
        for e in b.upcoming:
            days = (e.day - b.ctx.today).days
            when = "today" if days == 0 else "tomorrow" if days == 1 else f"{e.day:%a %b %d}"
            sector_note = f" (moves {e.scope[0]})" if ev.MARKET not in e.scope and len(e.scope) > 1 else ""
            L.append(f"• {when}: {e.name}{sector_note}")
    else:
        L.append("• no scheduled macro events")
    return "\n".join(L)


def _move_bits(v: HoldingView) -> list[str]:
    bits = []
    if v.change_1d is not None:
        bits.append(f"{v.change_1d:+.1f}% last session")
    if v.pnl_pct is not None:
        bits.append(f"{v.pnl_pct:+.0f}% vs cost")
    if v.value:
        bits.append(money(v.value))
    return bits


def _deep_block(v: HoldingView, b: BriefData) -> list[str]:
    s, h = v.signal, v.holding
    head = f"*{h.symbol}* ${v.price:,.2f}" if v.price else f"*{h.symbol}*"
    L = [head + (" · " + " · ".join(_move_bits(v)) if _move_bits(v) else "")]
    if v.fund:
        lv = v.lev
        px = f" ${lv.under_price:,.2f}" if lv and lv.under_price else ""
        ch = f" ({lv.under_change_1d:+.1f}%)" if lv and lv.under_change_1d is not None else ""
        L.append(f"   {v.fund.label}{px}{ch}")
    L.append(f"   ↳ Rules: {rules_say(s)}")
    if v.fundamentals:
        label = v.company if v.fund else "Company"
        L += [f"   • {x}" for x in v.fundamentals.lines(v.company_price, label)]
    if v.lev:
        L += [f"   • {x}" for x in v.lev.lines(h.cost)]
    levels = []
    if s.levels and s.levels.support:
        levels.append(f"support ${s.levels.support[0]:,.2f}")
    if s.levels and s.levels.resistance:
        levels.append(f"resistance ${s.levels.resistance[0]:,.2f}")
    if levels:
        L.append(f"   • {h.symbol} " + " · ".join(levels))
    if s.earnings and s.earnings.status == "known":
        L.append("   • " + (f"{v.company} " if v.fund else "") + s.earnings.describe(b.ctx.today))
    if s.sector and s.sector.blocks_calls:
        L.append(f"   • sector {s.sector.detail}")
    return L


def _short_line(v: HoldingView, b: BriefData) -> str:
    s, h = v.signal, v.holding
    head = f"• *{h.symbol}* ${v.price:,.2f}" if v.price else f"• *{h.symbol}*"
    bits = _move_bits(v)
    out = head + (f" ({', '.join(bits)})" if bits else "")
    tail = [f"{v.fund.label}"] if v.fund else []
    tail.append(rules_short(s))
    if s.earnings and s.earnings.status == "known" and s.earnings.days_until(b.ctx.today) is not None \
            and 0 <= s.earnings.days_until(b.ctx.today) <= 30:
        tail.append((f"{v.company} " if v.fund else "") + s.earnings.describe(b.ctx.today))
    return out + " – " + " · ".join(tail)


def _totals(b: BriefData) -> list[str]:
    L = []
    vals = [v for v in b.holdings if v.value]
    if vals:
        value = sum(v.value for v in vals)
        line = f"Stocks/ETFs {money(value)}"
        costed = [v for v in vals if v.basis]
        if costed:
            cv, basis = sum(v.value for v in costed), sum(v.basis for v in costed)
            pct = (cv / basis - 1) * 100
            if len(costed) == len(vals):
                line += f" vs cost {money(basis)} ({pct:+.0f}%)"
            else:
                line += f" · {len(costed)} with a cost: {money(cv)} vs {money(basis)} ({pct:+.0f}%)"
        moved = [v for v in vals if v.day_pnl is not None]
        day = sum(v.day_pnl for v in moved)
        base = sum(v.holding.shares * v.prev_close for v in moved)
        if day and base > 0:
            line += f" · last session {money(day, sign=True)} ({day / base * 100:+.1f}%)"
        L.append(line)
        lev_value = sum(v.value for v in vals if v.fund)
        if lev_value:
            L.append(f"Leveraged ETFs: {lev_value / value * 100:.0f}% of that – they reset daily and lose ground "
                     "in choppy markets even when the stock goes nowhere")
    priced = [o for o in b.options if o.value is not None and o.days_left >= 0]
    if priced:
        value = sum(o.value for o in priced)
        line = f"Options {money(value)}"
        paid = [o for o in priced if o.paid]
        if paid:
            pv, cost = sum(o.value for o in paid), sum(o.paid for o in paid)
            extra = "" if len(paid) == len(priced) else f" on the {len(paid)} with a cost"
            line += f" vs {money(cost)} paid ({money(pv - cost, sign=True)}{extra})"
        decay = sum(o.decay_day for o in priced if o.decay_day is not None)
        if abs(decay) >= 1:
            line += f" · time decay ≈ -{money(abs(decay))}/day" if decay < 0 else f" · time value ≈ +{money(decay)}/day"
        L.append(line)
    return L


def render_stocks(b: BriefData, ai_stocks: Optional[str] = None) -> str:
    owned = any(v.holding.shares or v.holding.cost for v in b.holdings)
    title = "Your stocks" if owned else "Stocks you follow"
    L = [f"📊 *{title} – {_date_line(b)}*"]
    tot = _totals(b)
    if tot:
        L += [""] + tot
    deep = [v for v in b.holdings if v.deep]
    rest = [v for v in b.holdings if not v.deep]
    for v in deep:
        L += [""] + _deep_block(v, b)
    if rest:
        L += ["", "*The rest*"] + [_short_line(v, b) for v in rest]

    if b.options:
        L += ["", "*Your options*"]
        for o in b.options:
            L += o.lines()
        L.append("_Ask of each: would I buy this contract today at today's price? Money already lost is gone "
                 "either way._")

    if b.watch:
        L += ["", "*Watchlist*"]
        for w in b.watch:
            icon = "🚨" if w.status == SIGNAL else "⏳"
            L.append(f"{icon} {w.symbol}: {w.headline}")

    if ai_stocks:
        L += ["", "*What the news says*", ai_stocks.strip()]
    else:
        heads = [(v.company, n) for v in deep for n in v.news[:1]]
        if heads:
            L += ["", "*Headlines*"]
            L += [f"• {sym}: {n['title']}" + (f" ({n['publisher']})" if n.get("publisher") else "") for sym, n in heads]

    L += ["", DISCLAIMER]
    return "\n".join(L)


def messages(b: BriefData, ai: Optional[AIText] = None, split: bool = True) -> list[str]:
    ai = ai or AIText()
    news, stocks = render_news(b, ai.news), render_stocks(b, ai.stocks)
    return [news, stocks] if split else [news + "\n\n" + stocks]


def render(b: BriefData, ai: Optional[AIText] = None) -> str:
    return messages(b, ai, split=False)[0]


# --------------------------------------------------------------------------- #
# AI section (Claude + web search)
# --------------------------------------------------------------------------- #

MARKER = "===STOCKS==="
_MARKER_RE = re.compile(r"[ \t*_]*={3,}\s*STOCKS\s*={3,}[ \t*_]*\n?", re.I)

AI_SYSTEM = """You write two parts of a daily WhatsApp brief for one retail trader who holds US \
stocks, leveraged ETFs and options and is learning how markets work. He runs a rule-based bot \
(Fibonacci EMA pullback entries, a market-regime score, an event veto); its numbers are in the facts.

Rules:
- Use web search for the last 24-48 hours of news. Prefer Reuters, AP, CNBC, Bloomberg, WSJ, FT, \
company filings and press releases. Use only numbers from the facts or from your search results.
- Do not tell him to buy, sell, hold or average down. Explain what is happening, what the bull and \
bear cases are, and what would change the picture. Phrase forecasts as possibilities.
- Write in {language}. WhatsApp formatting only: *bold*, _italic_, "•" bullets. No markdown \
headers, tables or links. Output only the two parts, no preamble.

PART 1 – market news (at most {news_chars} characters), exactly:
*What's moving markets*
• (2–3 bullets: the driver, and why it matters for stocks)
*Washington & the Fed*
• (what the White House, Congress, regulators and the Fed did or signaled that matters for \
stocks: tariffs, deadlines, Fed speakers. Include the market-implied odds for the next Fed \
decision if you find them, e.g. CME FedWatch or Kalshi, with the source)
*What the pros are saying*
• (one bullish and one bearish view, each attributed to a firm or strategist)
*Scenarios to watch*
• If <catalyst goes one way> → <likely market reaction> → <what the bot's rules would do>
*Lesson of the day*
(2–3 sentences explaining one concept using today's data)

Then a line containing exactly {marker}

PART 2 – his stocks (at most {stock_chars} characters). For each symbol in "focus" (at most \
{n_focus}), one block; for a leveraged ETF write about the company behind it and name both:
*SYMBOL*
• Why it moved: (recent news, with the source name)
• Bull case: (one line, attributed when it comes from an analyst)
• Bear case: (one line)
• Next catalyst: (date and what to watch)
Skip a symbol if you found nothing new about it."""


def facts_for_ai(b: BriefData) -> dict:
    r = b.ctx.regime
    focus = [v for v in b.holdings if v.deep]
    return {
        "date": b.now.strftime("%A %B %d, %Y"),
        "weekend": b.weekend,
        "market_regime": {
            "mode": r.mode, "score": r.score,
            "components": [{"name": c.label, "on": c.on, "detail": c.detail} for c in r.components],
        },
        "market_snapshot": b.snapshot,
        "upcoming_events": [{"date": e.day.isoformat(), "name": e.name, "scope": e.scope_label} for e in b.upcoming],
        "focus": [v.holding.symbol + (f" (= {v.fund.label})" if v.fund else "") for v in focus],
        "holdings": [
            {
                "symbol": v.holding.symbol, "company": v.company, "price": v.price,
                "change_1d_pct": v.change_1d, "pnl_vs_cost_pct": v.pnl_pct, "value": v.value,
                "leveraged_etf": v.fund.label if v.fund else None,
                "decay": v.lev.lines(v.holding.cost) if v.lev else None,
                "bot_status": v.signal.headline, "rules_say": rules_say(v.signal),
                "fundamentals": v.fundamentals.lines(v.company_price) if v.fundamentals else None,
                "support": v.signal.levels.support[:2] if v.signal.levels else [],
                "resistance": v.signal.levels.resistance[:2] if v.signal.levels else [],
                "earnings": v.signal.earnings.describe(b.ctx.today) if v.signal.earnings else None,
                "sector": v.signal.sector.detail if v.signal.sector else None,
                "yahoo_headlines": [n["title"] for n in v.news],
            }
            for v in b.holdings
        ],
        "options": [{"contract": o.holding.label, "lines": o.lines()} for o in b.options],
        "watchlist_signals": [{"symbol": w.symbol, "status": w.headline} for w in b.watch],
    }


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _cut(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) > limit + 400:
        text = text[: limit + 400].rsplit("\n", 1)[0] + "\n…"
    return text


def _with_sources(text: str, sources: list[str]) -> Optional[str]:
    if not text:
        return None
    if sources:
        text += "\n_Sources: " + ", ".join(sources[:5]) + "_"
    return text


def ai_take(b: BriefData, settings: Settings, news_chars: int = 1800, stock_chars: int = 1800) -> Optional[AIText]:
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic package not installed – skipping AI section")
        return None

    # bounded: one retry, 2 minutes per call, at most 3 continuations
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=120, max_retries=1)
    n_focus = max(1, min(settings.brief_deep_stocks, 8))
    system = AI_SYSTEM.format(language=settings.brief_language, news_chars=news_chars, stock_chars=stock_chars,
                              marker=MARKER, n_focus=n_focus)
    user = ("Facts from the bot (JSON):\n" + json.dumps(facts_for_ai(b), default=str, indent=1) +
            ("\n\nIt is the weekend: focus on the week ahead." if b.weekend else ""))
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": settings.brief_max_searches}]
    blocks: list = []  # every assistant content block so far, across pause_turn continuations
    try:
        for _ in range(4):
            messages_ = [{"role": "user", "content": user}]
            if blocks:
                messages_.append({"role": "assistant", "content": blocks})
            resp = client.messages.create(model=settings.brief_model, max_tokens=6000, system=system,
                                          messages=messages_, tools=tools)
            blocks = blocks + list(resp.content)
            if resp.stop_reason != "pause_turn":
                break
        if resp.stop_reason == "max_tokens":
            log.warning("AI section hit max_tokens – it may be cut short")
    except Exception as exc:
        log.error("AI brief failed: %s", type(exc).__name__)
        return None

    focus = [x for v in b.holdings if v.deep for x in (v.holding.symbol, v.company)]
    news, news_src, stocks, stock_src = split_ai(blocks, focus)
    news = _with_sources(_cut(news, news_chars), news_src)
    stocks = _with_sources(_cut(stocks, stock_chars), stock_src)
    if not news and not stocks:
        return None
    return AIText(news, stocks)


_NEWS_HEAD = re.compile(r"^[ \t*_]*What.s moving markets", re.I | re.M)


def split_ai(blocks: list, focus: list[str]) -> tuple[str, list[str], str, list[str]]:
    """Turn the model's content blocks into (news, news sources, stocks, stock sources).

    The model may search between the two parts, so the marker is looked for
    across all text blocks joined together, not just the ones after the last
    search. Short "let me search…" narration right before a search is
    dropped. Without a marker, part 2 starts at the first focus-symbol header.
    """
    kept: list[tuple[int, int, object]] = []  # (start, end, block) in the joined text
    text = ""
    for i, blk in enumerate(blocks):
        if blk.type != "text" or not blk.text.strip():
            continue
        nxt = blocks[i + 1].type if i + 1 < len(blocks) else None
        t = blk.text
        if (nxt == "server_tool_use" and len(t.strip()) < 400 and not _MARKER_RE.search(t)
                and not _NEWS_HEAD.search(t)):
            continue  # narration before a search
        kept.append((len(text), len(text) + len(t), blk))
        text += t

    m = _MARKER_RE.search(text)
    if m:
        cut, resume = m.start(), m.end()
    else:
        cut = resume = len(text)
        if focus:
            names = "|".join(re.escape(x) for x in dict.fromkeys(focus))
            h = re.search(rf"^[ \t]*\*\s*(?:{names})\b", text, re.M)
            if h and h.start() > 0:
                cut = resume = h.start()
    heads = [x.start() for x in _NEWS_HEAD.finditer(text[:cut])]
    start = heads[-1] if heads else 0  # drop any preamble before the news header

    sources: list[list[str]] = [[], []]
    for a, z, blk in kept:
        if z <= start:
            continue
        part = 0 if (a + z) / 2 < cut else 1
        for c in getattr(blk, "citations", None) or []:
            url = getattr(c, "url", None)
            if url and _domain(url) not in sources[part]:
                sources[part].append(_domain(url))
    return text[start:cut].strip(), sources[0], text[resume:].strip(), sources[1]


def build_messages(settings: Settings, now: Optional[datetime] = None, use_ai: bool = True) -> list[str]:
    b = gather(settings, now)
    return messages(b, ai_take(b, settings) if use_ai else None, split=settings.brief_split)


def build(settings: Settings, now: Optional[datetime] = None, use_ai: bool = True) -> str:
    return "\n\n".join(build_messages(settings, now, use_ai))
