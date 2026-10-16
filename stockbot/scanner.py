"""Scan orchestration: build one shared context, then evaluate symbols.

One batched download covers the watchlist, the sector ETFs and the market
inputs; earnings are only looked up for symbols whose trend gates pass (or on
request), which keeps Yahoo calls to a minimum.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from . import data, events as ev, regime as rg, sector as sec
from .signals import Signal, evaluate

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


@dataclass
class Context:
    today: date
    regime: rg.Regime
    events: list[ev.Event] = field(default_factory=list)
    history: dict[str, pd.DataFrame] = field(default_factory=dict)
    sectors: dict[str, Optional[str]] = field(default_factory=dict)  # symbol -> ETF
    sector_states: dict[str, sec.SectorState] = field(default_factory=dict)
    market: dict[str, pd.DataFrame] = field(default_factory=dict)
    partial_bar: bool = False


def market_is_open(now: Optional[datetime] = None) -> bool:
    now = (now or datetime.now(ET)).astimezone(ET)
    if now.weekday() >= 5:
        return False
    return now.replace(hour=9, minute=30, second=0, microsecond=0) <= now < now.replace(hour=16, minute=0, second=0, microsecond=0)


def build_context(settings, symbols: Iterable[str], now: Optional[datetime] = None) -> Context:
    now = (now or datetime.now(ET)).astimezone(ET)
    today = now.date()
    symbols = [s.upper() for s in symbols]

    market, hy = rg.load_inputs()
    regime = rg.assess(market, hy, settings.regime)

    calendar, bellwethers = ev.load_calendar(settings.events_file)
    events = calendar + ev.bellwether_events(bellwethers, today)

    smap = sec.SectorMap(settings.data_dir / "sectors.json", settings.sector_overrides)
    sectors = {s: smap.get(s) for s in symbols} if settings.sector_guard else {}
    etfs = sorted({e for e in sectors.values() if e})

    wanted = [s for s in list(dict.fromkeys(symbols + etfs)) if s not in market]
    history = {**{k: v for k, v in market.items()}, **data.fetch_history(wanted)}
    states = {}
    for etf in etfs:
        st = sec.assess(etf, history.get(etf))
        if st:
            states[etf] = st

    partial = False
    spy = history.get(rg.SPY)
    if spy is not None and not spy.empty:
        partial = spy.index[-1].date() == today and market_is_open(now)
    if partial and settings.confirm_on_close:
        history = {k: (v[v.index.date < today] if not v.empty else v) for k, v in history.items()}
        partial = False

    log.info("Regime %s | %d events loaded | %d sector ETFs", regime.describe(), len(events), len(states))
    return Context(today, regime, events, history, sectors, states, market, partial)


def ensure_symbols(ctx: Context, settings, symbols: Iterable[str]) -> None:
    """Add history / sector data for symbols the context doesn't have yet."""
    new = [s.upper() for s in symbols if s.upper() not in ctx.history]
    if not new:
        return
    if settings.sector_guard:
        smap = sec.SectorMap(settings.data_dir / "sectors.json", settings.sector_overrides)
        for s in new:
            ctx.sectors[s] = smap.get(s)
    etfs = {ctx.sectors.get(s) for s in new} - {None} - set(ctx.sector_states)
    ctx.history.update(data.fetch_history(new + sorted(etfs)))
    for etf in etfs:
        st = sec.assess(etf, ctx.history.get(etf))
        if st:
            ctx.sector_states[etf] = st


def analyze(symbol: str, ctx: Context, settings, force_earnings: bool = False) -> Signal:
    sym = symbol.upper()
    df = ctx.history.get(sym)
    etf = ctx.sectors.get(sym)
    state = ctx.sector_states.get(etf) if etf else None
    kwargs = dict(
        p=settings.strategy, regime=ctx.regime, risk=settings.risk, account_size=settings.account_size,
        risk_pct=settings.risk_pct, today=ctx.today, partial_bar=ctx.partial_bar, events=ctx.events, sector=state,
    )
    sig = evaluate(sym, df, **kwargs)
    if force_earnings or sig.direction is not None:
        sig = evaluate(sym, df, earnings=data.get_next_earnings(sym, ctx.today), **kwargs)
    return sig


def analyze_many(symbols: Iterable[str], settings, ctx: Optional[Context] = None,
                 force_earnings: bool = False) -> tuple[Context, list[Signal]]:
    symbols = list(dict.fromkeys(s.upper() for s in symbols))
    ctx = ctx or build_context(settings, symbols)
    out = []
    for sym in symbols:
        try:
            out.append(analyze(sym, ctx, settings, force_earnings))
        except Exception as exc:
            log.exception("analysis failed for %s: %s", sym, exc)
    return ctx, out
