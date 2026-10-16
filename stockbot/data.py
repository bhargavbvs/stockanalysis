"""Market data access (Yahoo Finance through yfinance).

Two fixes over the old code live here:

* History is downloaded for the whole watchlist in one batched request instead
  of one ``Ticker.history()`` + ``Ticker.info`` round trip per symbol.
* Earnings dates come from ``Ticker.calendar`` / ``get_earnings_dates``. The old
  analyzer read ``info["earningsDate"]``, a key yfinance does not return, so the
  earnings veto never fired.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional

import pandas as pd

log = logging.getLogger(__name__)

# The 200 EMA needs several times its span to converge; 1 year (the old
# default) is not enough, 3 years is.
HISTORY_PERIOD = "3y"
OHLCV = ("Open", "High", "Low", "Close", "Volume")


def _yf():
    import yfinance as yf  # imported lazily so tests never touch the network

    return yf


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Clean a raw OHLCV frame: drop empty rows, tz-naive daily index, floats."""
    keep = [c for c in OHLCV if c in df.columns]
    out = df.loc[:, keep].dropna(subset=["Close"])
    idx = pd.DatetimeIndex(out.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    out.index = idx.normalize()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    if "Volume" not in out:
        out["Volume"] = 0.0
    return out.astype(float)


def fetch_history(symbols: Iterable[str], period: str = HISTORY_PERIOD, retries: int = 2) -> dict[str, pd.DataFrame]:
    """Download daily bars for many symbols at once. Missing symbols are skipped."""
    pending = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
    out: dict[str, pd.DataFrame] = {}
    if not pending:
        return out

    yf = _yf()
    for attempt in range(retries + 1):
        try:
            raw = yf.download(
                pending,
                period=period,
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
        except Exception as exc:  # network / Yahoo hiccup
            log.warning("Download failed (attempt %d): %s", attempt + 1, exc)
            raw = None

        if raw is not None and not raw.empty:
            for sym in pending:
                try:
                    sub = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
                except KeyError:
                    continue
                sub = normalize(sub)
                if not sub.empty:
                    out[sym] = sub

        pending = [s for s in pending if s not in out]
        if not pending:
            break
        if attempt < retries:
            time.sleep(2 * (attempt + 1))

    if pending:
        log.warning("No price data for: %s", ", ".join(pending))
    return out


# --------------------------------------------------------------------------- #
# Earnings
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EarningsInfo:
    """Next earnings date.

    status: "known"   – a future date was found
            "none"    – the lookup worked but there is no upcoming date (ETFs etc.)
            "unknown" – the lookup failed; treat with caution, not as "clear"
    """

    status: str
    next_date: Optional[date] = None

    def days_until(self, today: date) -> Optional[int]:
        if self.next_date is None:
            return None
        return (self.next_date - today).days

    def within(self, today: date, days: int) -> Optional[bool]:
        """True/False if we know, None if the lookup failed."""
        if self.status == "unknown":
            return None
        d = self.days_until(today)
        return d is not None and 0 <= d <= days

    def describe(self, today: date) -> str:
        if self.status == "unknown":
            return "earnings date unavailable"
        if self.next_date is None:
            return "no upcoming earnings date"
        d = self.days_until(today)
        return f"earnings {self.next_date:%b %d} ({d} days)"


def _to_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date()
    try:
        return pd.Timestamp(value).date()
    except Exception:
        return None


_EARNINGS_CACHE: dict[tuple[str, date], EarningsInfo] = {}


def get_next_earnings(symbol: str, today: Optional[date] = None) -> EarningsInfo:
    """Next earnings date for `symbol`, cached per calendar day."""
    today = today or date.today()
    key = (symbol.upper(), today)
    if key in _EARNINGS_CACHE:
        return _EARNINGS_CACHE[key]

    info = EarningsInfo("unknown")
    lookup_ok = False
    try:
        ticker = _yf().Ticker(symbol)
        try:
            cal = ticker.calendar or {}
            lookup_ok = True
            dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if dates is not None and not isinstance(dates, (list, tuple)):
                dates = [dates]
            future = sorted(d for d in (_to_date(x) for x in (dates or [])) if d and d >= today)
            if future:
                info = EarningsInfo("known", future[0])
        except Exception as exc:
            log.debug("calendar lookup failed for %s: %s", symbol, exc)

        if info.status != "known":
            try:
                ed = ticker.get_earnings_dates(limit=8)
                lookup_ok = True
                if ed is not None and not ed.empty:
                    future = sorted(d for d in (_to_date(x) for x in ed.index) if d and d >= today)
                    if future:
                        info = EarningsInfo("known", future[0])
            except Exception as exc:
                log.debug("earnings_dates lookup failed for %s: %s", symbol, exc)

        if info.status != "known" and lookup_ok:
            info = EarningsInfo("none")
    except Exception as exc:
        log.debug("earnings lookup failed for %s: %s", symbol, exc)

    _EARNINGS_CACHE[key] = info
    return info


def fetch_fred(series_id: str, timeout: int = 15) -> Optional[pd.Series]:
    """A FRED series as a date-indexed float Series (no API key needed)."""
    import io

    import requests

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
    except Exception as exc:
        log.warning("FRED %s unavailable: %s", series_id, exc)
        return None
    df.columns = ["date", "value"]
    s = pd.to_numeric(df["value"], errors="coerce")
    s.index = pd.to_datetime(df["date"])
    return s.dropna()


def fetch_news(symbol: str, limit: int = 5) -> list[dict]:
    """Recent headlines from Yahoo Finance: [{'title', 'publisher', 'url', 'published'}]."""
    try:
        items = _yf().Ticker(symbol).news or []
    except Exception as exc:
        log.debug("news unavailable for %s: %s", symbol, exc)
        return []
    out = []
    for item in items:
        c = item.get("content", item)  # yfinance >= 0.2.50 nests under "content"
        title = c.get("title")
        if not title:
            continue
        provider = c.get("provider") or {}
        link = (c.get("canonicalUrl") or c.get("clickThroughUrl") or {})
        out.append({
            "title": title,
            "publisher": provider.get("displayName") if isinstance(provider, dict) else c.get("publisher"),
            "url": link.get("url") if isinstance(link, dict) else c.get("link"),
            "published": c.get("pubDate") or c.get("providerPublishTime"),
        })
        if len(out) >= limit:
            break
    return out


def get_earnings_history(symbol: str, limit: int = 60) -> Optional[list[date]]:
    """Past and scheduled earnings dates (for the backtest). None if unavailable."""
    try:
        ed = _yf().Ticker(symbol).get_earnings_dates(limit=limit)
    except Exception as exc:
        log.debug("earnings history unavailable for %s: %s", symbol, exc)
        return None
    if ed is None or ed.empty:
        return None
    return sorted({d for d in (_to_date(x) for x in ed.index) if d})
