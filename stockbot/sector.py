"""Sector guard.

The June and October 2026 chip sell-offs were sector crashes inside an index
that barely moved, so index-level filters missed them. Each stock is mapped to
a sector ETF and new CALLs are blocked when that sector is either

  * extended:   14-day RSI > 75, or price > 20% above its 50-day SMA
                (SOX was RSI ~80 and +35% above its 50-day before June 5, 2026)
  * breaking:   closed below its 21 EMA for 3 sessions with the 21 EMA falling
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from .indicators import ema, rsi

log = logging.getLogger(__name__)

SEMIS = "SOXX"
SECTOR_ETFS = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}


@dataclass(frozen=True)
class SectorParams:
    rsi_max: float = 75.0
    ext_pct: float = 20.0
    below_days: int = 3


@dataclass
class SectorState:
    etf: str
    extended: bool
    breaking: bool
    rsi: Optional[float]
    pct_above_50: Optional[float]
    detail: str

    @property
    def blocks_calls(self) -> bool:
        return self.extended or self.breaking


def sector_frame(etf: pd.DataFrame, p: SectorParams = SectorParams()) -> pd.DataFrame:
    close = etf["Close"]
    out = pd.DataFrame(index=etf.index)
    out["rsi"] = rsi(close, 14)
    sma50 = close.rolling(50).mean()
    out["pct_above_50"] = (close / sma50 - 1) * 100
    e21 = ema(close, 21)
    below = (close < e21).astype(int)
    out["below_streak"] = below.groupby((below == 0).cumsum()).cumsum()
    out["e21_falling"] = e21 < e21.shift(1)
    out["extended"] = ((out["rsi"] > p.rsi_max) | (out["pct_above_50"] > p.ext_pct)).fillna(False)
    out["breaking"] = ((out["below_streak"] >= p.below_days) & out["e21_falling"]).fillna(False)
    return out


def assess(etf_symbol: str, etf: Optional[pd.DataFrame], p: SectorParams = SectorParams()) -> Optional[SectorState]:
    if etf is None or len(etf) < 60:
        return None
    r = sector_frame(etf, p).iloc[-1]
    rsi_v = None if pd.isna(r.rsi) else float(r.rsi)
    ext_v = None if pd.isna(r.pct_above_50) else float(r.pct_above_50)
    parts = [f"{etf_symbol} RSI {rsi_v:.0f}" if rsi_v is not None else f"{etf_symbol}",
             f"{ext_v:+.0f}% vs 50-day" if ext_v is not None else ""]
    if r.extended:
        parts.append("EXTENDED")
    if r.breaking:
        parts.append(f"below 21 EMA {int(r.below_streak)} days, 21 EMA falling")
    return SectorState(etf_symbol, bool(r.extended), bool(r.breaking), rsi_v, ext_v, ", ".join(x for x in parts if x))


class SectorMap:
    """symbol -> sector ETF, from yfinance profile data, cached on disk."""

    def __init__(self, cache_file: Path, overrides: Optional[dict[str, str]] = None):
        self.cache_file = Path(cache_file)
        self.overrides = {k.upper(): v.upper() for k, v in (overrides or {}).items()}
        try:
            self.cache: dict[str, Optional[str]] = json.loads(self.cache_file.read_text())
        except Exception:
            self.cache = {}

    def get(self, symbol: str) -> Optional[str]:
        sym = symbol.upper()
        if sym in self.overrides:
            return self.overrides[sym]
        if sym in self.cache:
            return self.cache[sym]
        etf, ok = self._lookup(sym)
        if not ok:  # network failure: don't cache, try again next time
            return None
        self.cache[sym] = etf
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps(self.cache, indent=1, sort_keys=True))
        except Exception as exc:
            log.debug("could not write sector cache: %s", exc)
        return etf

    @staticmethod
    def _lookup(sym: str) -> tuple[Optional[str], bool]:
        try:
            from .data import _yf

            info = _yf().Ticker(sym).info or {}
        except Exception as exc:
            log.debug("sector lookup failed for %s: %s", sym, exc)
            return None, False
        if not info:
            return None, False
        if info.get("quoteType") in ("ETF", "INDEX", "MUTUALFUND", "CRYPTOCURRENCY"):
            return None, True
        if "semiconductor" in str(info.get("industry", "")).lower():
            return SEMIS, True
        return SECTOR_ETFS.get(info.get("sector", "")), True
