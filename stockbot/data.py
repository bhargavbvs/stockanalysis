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
import math
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


FUND_TYPES = ("ETF", "INDEX", "MUTUALFUND", "CRYPTOCURRENCY", "FUTURE", "CURRENCY")


def get_next_earnings(symbol: str, today: Optional[date] = None) -> EarningsInfo:
    """Next earnings date for `symbol`.

    Fails closed: "none" is only returned with positive evidence (an earnings
    table without a future date, or a fund that has no earnings). yfinance
    swallows HTTP errors and hands back empty results, which must not be read
    as "no earnings coming". Known/none results are cached for the day;
    "unknown" is retried on the next call.
    """
    today = today or date.today()
    key = (symbol.upper(), today)
    if key in _EARNINGS_CACHE:
        return _EARNINGS_CACHE[key]
    info = _lookup_earnings(symbol, today)
    if info.status != "unknown":
        _EARNINGS_CACHE[key] = info
    return info


def _future(values, today: date) -> list[date]:
    return sorted(d for d in (_to_date(x) for x in values) if d and d >= today)


def _lookup_earnings(symbol: str, today: date) -> EarningsInfo:
    try:
        ticker = _yf().Ticker(symbol)
    except Exception as exc:
        log.debug("earnings lookup failed for %s: %s", symbol, type(exc).__name__)
        return EarningsInfo("unknown")

    no_future_evidence = False
    try:
        cal = ticker.calendar
        if isinstance(cal, dict) and "Earnings Date" in cal:
            dates = cal.get("Earnings Date")
            dates = dates if isinstance(dates, (list, tuple)) else [dates]
            fut = _future(dates, today)
            if fut:
                return EarningsInfo("known", fut[0])
            if any(_to_date(x) for x in dates):  # only past dates listed
                no_future_evidence = True
    except Exception as exc:
        log.debug("calendar lookup failed for %s: %s", symbol, type(exc).__name__)

    try:
        ed = ticker.get_earnings_dates(limit=12)
        if ed is not None and not ed.empty:
            fut = _future(ed.index, today)
            if fut:
                return EarningsInfo("known", fut[0])
            no_future_evidence = True
    except Exception as exc:
        log.debug("earnings_dates lookup failed for %s: %s", symbol, type(exc).__name__)

    if no_future_evidence:
        return EarningsInfo("none")
    try:
        if (ticker.info or {}).get("quoteType") in FUND_TYPES:
            return EarningsInfo("none")
    except Exception as exc:
        log.debug("quoteType lookup failed for %s: %s", symbol, type(exc).__name__)
    return EarningsInfo("unknown")


def fetch_fred(series_id: str, timeout: int = 15) -> Optional[pd.Series]:
    """A FRED series as a date-indexed float Series (no API key needed).

    Returns None on any failure, including a non-CSV response (FRED serves an
    HTML page during maintenance), so a FRED outage never breaks a scan.
    """
    import io

    import requests

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        if df.shape[1] != 2 or df.empty:
            raise ValueError(f"unexpected FRED response shape {df.shape}")
        s = pd.to_numeric(df.iloc[:, 1], errors="coerce")
        s.index = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        s = s[s.index.notna()].dropna()
        if s.empty:
            raise ValueError("no numeric observations")
        return s
    except Exception as exc:
        log.warning("FRED %s unavailable: %s", series_id, type(exc).__name__)
        return None


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


@dataclass
class Fundamentals:
    """Company facts for the brief. Every field is optional; Yahoo leaves gaps."""

    symbol: str
    name: Optional[str] = None
    revenue_growth: Optional[float] = None  # latest quarter vs a year earlier, %
    net_margin: Optional[float] = None  # latest quarter, % (falls back to trailing 12 months)
    pe: Optional[float] = None
    forward_pe: Optional[float] = None
    buy: Optional[int] = None
    hold: Optional[int] = None
    sell: Optional[int] = None
    analysts: Optional[int] = None
    target_mean: Optional[float] = None
    target_low: Optional[float] = None
    target_high: Optional[float] = None

    def lines(self, price: Optional[float], label: str = "") -> list[str]:
        who = f"{label}: " if label else ""
        biz = []
        if self.revenue_growth is not None:
            biz.append(f"revenue {self.revenue_growth:+.0f}% y/y")
        if self.net_margin is not None:
            biz.append(f"net margin {self.net_margin:.0f}%")
        if self.pe is not None and self.pe > 0:
            biz.append(f"P/E {self.pe:.0f}" + (f" (fwd {self.forward_pe:.0f})" if self.forward_pe and self.forward_pe > 0 else ""))
        elif self.pe is None and self.net_margin is not None and self.net_margin < 0:
            biz.append("not profitable yet")
        out = [f"{who}" + " · ".join(biz)] if biz else []
        street = []
        if self.buy is not None:
            street.append(f"{self.buy} Buy / {self.hold or 0} Hold / {self.sell or 0} Sell")
        elif self.analysts:
            street.append(f"{self.analysts} analysts")
        if self.target_mean:
            up = f" ({(self.target_mean / price - 1) * 100:+.0f}%)" if price else ""
            rng = (f", range ${self.target_low:,.0f}–{self.target_high:,.0f}"
                   if self.target_low and self.target_high else "")
            street.append(f"avg target ${self.target_mean:,.2f}{up}{rng}")
        if street:
            out.append("Analysts: " + " · ".join(street))
        return out


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _row(df: pd.DataFrame, *names: str) -> Optional[pd.Series]:
    for n in names:
        if n in df.index:
            return pd.to_numeric(df.loc[n], errors="coerce")
    return None


_FUND_CACHE: dict[tuple[str, date], Optional[Fundamentals]] = {}


def fetch_fundamentals(symbol: str, today: Optional[date] = None) -> Optional[Fundamentals]:
    """Growth, margin, valuation and analyst consensus from Yahoo. None if nothing came back."""
    key = (symbol.upper(), today or date.today())
    if key in _FUND_CACHE:
        return _FUND_CACHE[key]
    try:
        t = _yf().Ticker(symbol)
    except Exception as exc:
        log.debug("fundamentals unavailable for %s: %s", symbol, type(exc).__name__)
        return None
    f = Fundamentals(symbol.upper())
    try:
        info = t.info or {}
    except Exception:
        info = {}
    if info.get("quoteType") in FUND_TYPES:
        return None
    f.name = info.get("shortName")
    f.pe, f.forward_pe = _num(info.get("trailingPE")), _num(info.get("forwardPE"))
    g, m = _num(info.get("revenueGrowth")), _num(info.get("profitMargins"))
    f.revenue_growth = None if g is None else g * 100
    f.net_margin = None if m is None else m * 100
    f.analysts = int(info["numberOfAnalystOpinions"]) if _num(info.get("numberOfAnalystOpinions")) else None
    f.target_mean, f.target_low, f.target_high = (_num(info.get(k)) for k in
                                                   ("targetMeanPrice", "targetLowPrice", "targetHighPrice"))
    try:  # the latest quarter beats Yahoo's trailing figures for fast movers
        q = t.quarterly_income_stmt
        if q is not None and not q.empty:
            q = q.reindex(sorted(q.columns, reverse=True), axis=1)
            rev, ni = _row(q, "Total Revenue", "Operating Revenue"), _row(q, "Net Income", "Net Income Common Stockholders")
            if rev is not None and len(rev.dropna()) and rev.iloc[0] and rev.iloc[0] > 0:
                latest = pd.Timestamp(rev.index[0])
                for col, val in rev.iloc[1:].items():  # the quarter ~1 year earlier, matched by date
                    if 350 <= (latest - pd.Timestamp(col)).days <= 380 and val and val > 0:
                        f.revenue_growth = (rev.iloc[0] / val - 1) * 100
                        break
                if ni is not None and _num(ni.iloc[0]) is not None:
                    f.net_margin = ni.iloc[0] / rev.iloc[0] * 100
    except Exception as exc:
        log.debug("income statement unavailable for %s: %s", symbol, type(exc).__name__)
    try:
        rec = t.recommendations
        if rec is not None and not rec.empty:
            row = rec[rec["period"] == "0m"].iloc[0] if "period" in rec and (rec["period"] == "0m").any() else rec.iloc[0]
            g_ = lambda k: int(_num(row.get(k)) or 0)  # noqa: E731
            f.buy, f.hold, f.sell = g_("strongBuy") + g_("buy"), g_("hold"), g_("sell") + g_("strongSell")
            if not (f.buy or f.hold or f.sell):
                f.buy = f.hold = f.sell = None
    except Exception as exc:
        log.debug("recommendations unavailable for %s: %s", symbol, type(exc).__name__)
    empty = all(getattr(f, k) is None for k in ("revenue_growth", "net_margin", "pe", "buy", "target_mean"))
    out = None if empty else f
    if out is not None:
        _FUND_CACHE[key] = out
    return out


def fetch_option_quote(underlying: str, expiry: date, strike: float, right: str):
    """Yahoo quote for one contract -> options.OptionQuote, or None."""
    from .options import OptionQuote

    try:
        t = _yf().Ticker(underlying)
        exp = expiry.isoformat()
        if exp not in (t.options or ()):
            log.warning("%s has no %s expiry on Yahoo", underlying, exp)
            return None
        chain = t.option_chain(exp)
        table = chain.calls if right == "C" else chain.puts
        row = table[(table["strike"] - strike).abs() < 1e-6]
        if row.empty:
            return None
        r = row.iloc[0]
        return OptionQuote(_num(r.get("bid")), _num(r.get("ask")), _num(r.get("lastPrice")), _num(r.get("impliedVolatility")))
    except Exception as exc:
        log.debug("option quote unavailable for %s %s %s%s: %s", underlying, expiry, strike, right, type(exc).__name__)
        return None


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
