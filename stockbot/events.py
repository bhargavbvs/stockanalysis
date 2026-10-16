"""Macro event calendar and event veto.

Prices absorb headlines within minutes, so the bot doesn't try to trade news.
What *is* knowable in advance is when risk is concentrated: CPI, jobs, FOMC,
bellwether earnings, policy deadlines. New entries are vetoed on the session
before such an event and on the event day.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from . import marketcal

log = logging.getLogger(__name__)

MARKET = "market"


@dataclass(frozen=True)
class Event:
    day: date
    name: str
    scope: tuple[str, ...] = (MARKET,)

    def applies_to(self, symbol: str, sector_etf: Optional[str]) -> bool:
        s = {x.upper() for x in self.scope}
        return MARKET.upper() in s or symbol.upper() in s or (sector_etf is not None and sector_etf.upper() in s)

    @property
    def scope_label(self) -> str:
        return "all stocks" if MARKET in self.scope else ", ".join(self.scope)


def _scope(value) -> tuple[str, ...]:
    if value is None:
        return (MARKET,)
    if isinstance(value, str):
        return (value if value == MARKET else value.upper(),)
    return tuple(str(v).upper() for v in value)


def load_calendar(path: str | Path = "events.yaml") -> tuple[list[Event], dict[str, list[str]]]:
    """Read events.yaml -> (events, bellwethers by sector ETF)."""
    p = Path(path)
    if not p.exists():
        log.warning("event calendar %s not found – event veto limited to bellwether earnings", p)
        return [], {}
    import yaml

    raw = yaml.safe_load(p.read_text()) or {}
    events = []
    for item in raw.get("events") or []:
        try:
            events.append(Event(pd.Timestamp(item["date"]).date(), str(item["name"]), _scope(item.get("scope"))))
        except Exception as exc:
            log.warning("skipping bad event %r: %s", item, exc)
    bell = {str(k).upper(): [str(s).upper() for s in v] for k, v in (raw.get("bellwethers") or {}).items()}
    return sorted(events, key=lambda e: e.day), bell


def bellwether_events(bellwethers: dict[str, list[str]], today: date, horizon_days: int = 21) -> list[Event]:
    """Upcoming earnings of sector bellwethers as sector-scoped events (network)."""
    from .data import get_next_earnings

    out = []
    for etf, symbols in bellwethers.items():
        for sym in symbols:
            info = get_next_earnings(sym, today)
            d = info.days_until(today)
            if info.status == "known" and d is not None and 0 <= d <= horizon_days:
                out.append(Event(info.next_date, f"{sym} earnings", (etf, sym)))
    return sorted(out, key=lambda e: e.day)


def next_session(day: date) -> date:
    """Next NYSE trading day (skips weekends and exchange holidays)."""
    return marketcal.next_session(day)


def calendar_runs_out(events: Iterable[Event], today: date, warn_days: int = 45) -> Optional[date]:
    """Last scheduled market-wide event if it is less than `warn_days` away."""
    market = [e.day for e in events if MARKET in e.scope]
    last = max(market) if market else None
    if last is None or (last - today).days < warn_days:
        return last or today
    return None


def blocking_event(events: Iterable[Event], today: date, symbol: str,
                   sector_etf: Optional[str] = None) -> Optional[Event]:
    """The event that vetoes a new entry today, if any (event today or next session)."""
    window_end = next_session(today)
    for e in events:
        if today <= e.day <= window_end and e.applies_to(symbol, sector_etf):
            return e
    return None


def upcoming(events: Iterable[Event], today: date, days: int = 7) -> list[Event]:
    return [e for e in events if 0 <= (e.day - today).days <= days]


def block_series(events: Iterable[Event], index: pd.DatetimeIndex, symbol: str,
                 sector_etf: Optional[str] = None) -> pd.Series:
    """Per-bar event veto (for the backtest)."""
    flags = pd.Series(False, index=index)
    days = index.normalize()
    for e in events:
        if e.applies_to(symbol, sector_etf):
            ev = pd.Timestamp(e.day)
            prev = pd.Timestamp(marketcal.prev_session(e.day))
            flags |= (days == ev) | (days == prev)
    return flags
