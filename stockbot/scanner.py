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

from . import data, events as ev, marketcal, regime as rg, sector as sec
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
    if not marketcal.is_trading_day(now.date()):
        return False
    ch, cm = marketcal.close_time(now.date())
    return now.replace(hour=9, minute=30, second=0, microsecond=0) <= now < now.replace(
        hour=ch, minute=cm, second=0, microsecond=0)


def _under(settings, symbol: str) -> str:
    """Leveraged ETFs are judged on the company behind them (SNXX -> SNDK) for earnings and sector."""
    fn = getattr(settings, "underlying", None)
    return fn(symbol) if fn else symbol


def _inverse(settings, symbol: str) -> bool:
    fund = getattr(settings, "leveraged", {}).get(symbol.upper())
    return fund is not None and fund.factor < 0


def sector_for(settings, smap: sec.SectorMap, symbol: str) -> Optional[str]:
    """Sector ETF: an explicit SECTOR_OVERRIDES entry wins, else the company behind a leveraged ETF."""
    if symbol.upper() in smap.overrides:
        return smap.get(symbol)
    return smap.get(_under(settings, symbol))


def _drop_partial(history: dict[str, pd.DataFrame], today: date) -> dict[str, pd.DataFrame]:
    return {k: (v[v.index.date < today] if not v.empty else v) for k, v in history.items()}


def build_context(settings, symbols: Iterable[str], now: Optional[datetime] = None) -> Context:
    now = (now or datetime.now(ET)).astimezone(ET)
    today = now.date()
    symbols = [s.upper() for s in symbols]

    market, hy = rg.load_inputs()
    spy = market.get(rg.SPY)
    partial = spy is not None and not spy.empty and spy.index[-1].date() == today and market_is_open(now)
    if partial and settings.confirm_on_close:
        market = _drop_partial(market, today)  # score the regime on closed bars too
    regime = rg.assess(market, hy, settings.regime)

    calendar, bellwethers = ev.load_calendar(settings.events_file)
    events = calendar + ev.bellwether_events(bellwethers, today)

    # Sector ETFs are always mapped (they scope bellwether-earnings vetoes);
    # SECTOR_GUARD only decides whether an overheated sector blocks CALLs.
    smap = sec.SectorMap(settings.data_dir / "sectors.json", settings.sector_overrides)
    sectors = {s: sector_for(settings, smap, s) for s in symbols}
    etfs = sorted({e for e in sectors.values() if e}) if settings.sector_guard else []

    wanted = [s for s in list(dict.fromkeys(symbols + etfs)) if s not in market]
    history = {**market, **data.fetch_history(wanted)}
    if partial and settings.confirm_on_close:
        history = _drop_partial(history, today)
        partial = False
    states = {}
    for etf in etfs:
        st = sec.assess(etf, history.get(etf))
        if st:
            states[etf] = st

    log.info("Regime %s | %d events loaded | %d sector ETFs", regime.describe(), len(events), len(states))
    return Context(today, regime, events, history, sectors, states, market, partial)


def ensure_symbols(ctx: Context, settings, symbols: Iterable[str]) -> None:
    """Add history / sector data for symbols the context doesn't have yet."""
    new = [s.upper() for s in symbols if s.upper() not in ctx.history]
    if not new:
        return
    smap = sec.SectorMap(settings.data_dir / "sectors.json", settings.sector_overrides)
    for s in new:
        ctx.sectors[s] = sector_for(settings, smap, s)
    etfs = ({ctx.sectors.get(s) for s in new} - {None} - set(ctx.sector_states)) if settings.sector_guard else set()
    ctx.history.update(data.fetch_history(new + sorted(etfs)))
    for etf in etfs:
        st = sec.assess(etf, ctx.history.get(etf))
        if st:
            ctx.sector_states[etf] = st


def analyze(symbol: str, ctx: Context, settings, force_earnings: bool = False) -> Signal:
    sym = symbol.upper()
    df = ctx.history.get(sym)
    etf = ctx.sectors.get(sym)
    # The guard blocks CALLs in an overheated/breaking sector. For an inverse fund a CALL is a bet *against*
    # that sector, so the guard doesn't apply (the ETF still scopes bellwether-earnings vetoes).
    state = ctx.sector_states.get(etf) if etf and not _inverse(settings, sym) else None
    kwargs = dict(
        p=settings.strategy, regime=ctx.regime, risk=settings.risk, account_size=settings.account_size,
        risk_pct=settings.risk_pct, today=ctx.today, partial_bar=ctx.partial_bar, events=ctx.events, sector=state,
        sector_etf=etf,
    )
    sig = evaluate(sym, df, **kwargs)
    if force_earnings or sig.direction is not None:
        sig = evaluate(sym, df, earnings=data.get_next_earnings(_under(settings, sym), ctx.today), **kwargs)
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
