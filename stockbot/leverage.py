"""Leveraged and inverse ETFs (SNXX = 2x SanDisk, TQQQ = 3x Nasdaq-100, ...).

A daily-reset fund delivers its multiple of the underlying's move for ONE
day. Over weeks, a choppy path costs it money even if the underlying ends
flat ("volatility decay"). For a constant volatility s and a holding period T
(in years), the fund's value ratio is approximately

    fund_ratio ~= underlying_ratio ** L * exp(-(L*L - L) / 2 * s*s * T)

so getting a 2x fund back to its cost basis takes more than half the
percentage move a straight-line path would need. This module maps funds to
their underlying (so earnings and sector checks use the real company) and
turns that formula into plain numbers for the brief.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LeveragedETF:
    etf: str
    underlying: str
    factor: float  # 2 for 2x long, -1 for 1x inverse, ...

    @property
    def label(self) -> str:
        f = self.factor
        side = "inverse " if f < 0 else ""
        mult = f"{abs(f):g}×"
        return f"{mult} {side}daily {self.underlying}"


# Verified single-stock and index funds. Extend or override with LEVERAGED_ETFS.
DEFAULT_LEVERAGED = {
    e.etf: e for e in (
        LeveragedETF("SNXX", "SNDK", 2), LeveragedETF("APLX", "APLD", 2), LeveragedETF("SOFX", "SOFI", 2),
        LeveragedETF("RCAX", "RCAT", 2), LeveragedETF("ONDG", "ONDS", 2),
        LeveragedETF("NVDL", "NVDA", 2), LeveragedETF("TSLL", "TSLA", 2),
        LeveragedETF("TQQQ", "QQQ", 3), LeveragedETF("SQQQ", "QQQ", -3),
        LeveragedETF("UPRO", "SPY", 3), LeveragedETF("SPXL", "SPY", 3), LeveragedETF("SPXU", "SPY", -3),
    )
}


def parse_leveraged(text: str, base: Optional[dict[str, LeveragedETF]] = None) -> dict[str, LeveragedETF]:
    """'SNXX:SNDK:2, SQQQ:QQQ:-3' merged over the defaults ('ETF:UNDERLYING' alone means 2x)."""
    out = dict(DEFAULT_LEVERAGED if base is None else base)
    for part in text.split(","):
        bits = [b.strip().upper() for b in part.split(":")]
        if not bits[0]:
            continue
        if len(bits) not in (2, 3) or not bits[1]:
            raise ValueError(f"LEVERAGED_ETFS entry {part.strip()!r} must look like SNXX:SNDK:2")
        try:
            factor = float(bits[2]) if len(bits) == 3 else 2.0
        except ValueError:
            raise ValueError(f"LEVERAGED_ETFS factor in {part.strip()!r} must be a number") from None
        if factor == 0:
            raise ValueError(f"LEVERAGED_ETFS factor in {part.strip()!r} can't be 0")
        out[bits[0]] = LeveragedETF(bits[0], bits[1], factor)
    return out


def underlying_needed(target_ratio: float, factor: float, vol: float, years: float) -> Optional[float]:
    """Underlying value ratio that brings the fund to `target_ratio` after `years` at volatility `vol`.

    With vol = 0 this is the straight-line answer (target ** (1/L)).
    """
    if target_ratio <= 0 or factor == 0:
        return None
    drag = (factor * factor - factor) / 2 * vol * vol * years
    return (target_ratio * math.exp(drag)) ** (1 / factor)


def realized_vol(close: pd.Series, days: int = 60) -> Optional[float]:
    r = np.log(close.astype(float)).diff().dropna().tail(days)
    if len(r) < 10:
        return None
    return float(r.std() * math.sqrt(252))


@dataclass
class LeverageView:
    fund: LeveragedETF
    under_price: Optional[float]
    under_change_1d: Optional[float]
    fund_ret: Optional[float]  # % over `window` sessions
    under_ret: Optional[float]
    window: int
    vol: Optional[float]  # underlying, annualized
    to_cost: Optional[float] = None  # % the fund needs to reach its cost basis
    straight: Optional[float] = None  # % underlying move, straight line
    with_swings: Optional[float] = None  # % underlying move over `horizon_days` of typical swings
    horizon_days: int = 63

    @property
    def lag(self) -> Optional[float]:
        """Points the fund fell short of factor x underlying over the window (positive = decay)."""
        if self.fund_ret is None or self.under_ret is None:
            return None
        return self.fund.factor * self.under_ret - self.fund_ret

    def lines(self, cost: Optional[float]) -> list[str]:
        f, out = self.fund, []
        if self.fund_ret is not None and self.under_ret is not None:
            tail = ""
            if self.lag is not None and self.lag > 2:
                tail = f" ({abs(f.factor):g}× would be {f.factor * self.under_ret:+.0f}%, decay cost {self.lag:.0f} pts)"
            out.append(f"Last {self.window} sessions: {f.underlying} {self.under_ret:+.0f}%, {f.etf} {self.fund_ret:+.0f}%{tail}")
        if cost and self.to_cost is not None and self.to_cost > 0 and self.straight is not None:
            months = round(self.horizon_days / 21)
            swing = (f", ~{self.with_swings:+.0f}% over {months} months of normal swings"
                     if self.with_swings is not None else "")
            out.append(f"Back to your ${cost:,.2f} ({self.to_cost:+.0f}%): {f.underlying} {self.straight:+.0f}% in a "
                       f"straight line{swing}")
        return out


def view(fund: LeveragedETF, fund_close: Optional[pd.Series], under_close: Optional[pd.Series],
         cost: Optional[float] = None, window: int = 21, horizon_days: int = 63) -> Optional[LeverageView]:
    if under_close is None or len(under_close) < 2:
        return None
    up = float(under_close.iloc[-1])
    uchg = (up / float(under_close.iloc[-2]) - 1) * 100
    fret = uret = None
    if fund_close is not None and len(fund_close) > window:
        both = pd.concat({"f": fund_close, "u": under_close}, axis=1, sort=True).dropna()
        if len(both) > window:
            fret = (both["f"].iloc[-1] / both["f"].iloc[-1 - window] - 1) * 100
            uret = (both["u"].iloc[-1] / both["u"].iloc[-1 - window] - 1) * 100
    vol = realized_vol(under_close)
    v = LeverageView(fund, up, uchg, fret, uret, window, vol, horizon_days=horizon_days)
    if cost and fund_close is not None and len(fund_close):
        target = cost / float(fund_close.iloc[-1])
        v.to_cost = (target - 1) * 100
        s = underlying_needed(target, fund.factor, 0.0, 0.0)
        v.straight = None if s is None else (s - 1) * 100
        if vol is not None:
            w = underlying_needed(target, fund.factor, vol, horizon_days / 252)
            v.with_swings = None if w is None else (w - 1) * 100
    return v
