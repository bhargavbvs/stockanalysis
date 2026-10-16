"""Market regime score (0–5).

Per-stock charts can look fine right up until the whole market rolls over
(April 2025 tariffs, the March 2026 oil shock). This layer scores the market
itself. One point for each condition that is on:

  1. Trend     SPY closes below its 50-day EMA
  2. Fear      VIX above 25, or up more than 30% in 5 sessions
  3. Panic     VIX above VIX3M (term structure inverted)
  4. Credit    High-yield spread (FRED BAMLH0A0HYM2) up > 0.40 pts in 20 sessions
  5. Macro     10-year yield up > 0.30 pts in 20 sessions, or Brent up > 20%

  0–1  NORMAL     full size
  2    CAUTION    half size, CALL alerts need HIGH confidence or better
  3–5  DEFENSIVE  no new CALLs (PUT setups get a confidence bump)

Credit and macro tend to move *before* a drawdown; VIX and term structure
mostly confirm it. Missing inputs count as "off" and are listed as unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from .indicators import ema

SPY, VIX, VIX3M, TNX, BRENT = "SPY", "^VIX", "^VIX3M", "^TNX", "BZ=F"
MARKET_SYMBOLS = (SPY, VIX, VIX3M, TNX, BRENT)
HY_SERIES = "BAMLH0A0HYM2"

NORMAL, CAUTION, DEFENSIVE = "NORMAL", "CAUTION", "DEFENSIVE"


@dataclass(frozen=True)
class RegimeParams:
    ema_span: int = 50
    vix_max: float = 25.0
    vix_spike_pct: float = 30.0
    vix_lookback: int = 5
    credit_bp: float = 0.40
    yield_bp: float = 0.30
    oil_pct: float = 20.0
    macro_lookback: int = 20
    caution_at: int = 2
    defensive_at: int = 3


@dataclass
class Component:
    key: str
    label: str
    on: bool
    detail: str
    available: bool = True


@dataclass
class Regime:
    asof: Optional[date]
    score: int = 0
    components: list[Component] = field(default_factory=list)
    params: RegimeParams = field(default_factory=RegimeParams)
    available: bool = True
    values: dict = field(default_factory=dict)

    @property
    def mode(self) -> str:
        if self.score >= self.params.defensive_at:
            return DEFENSIVE
        if self.score >= self.params.caution_at:
            return CAUTION
        return NORMAL

    @property
    def risk_off(self) -> bool:
        return self.available and self.mode == DEFENSIVE

    @property
    def size_multiplier(self) -> float:
        return {NORMAL: 1.0, CAUTION: 0.5, DEFENSIVE: 0.0}[self.mode]

    @property
    def reasons(self) -> list[str]:
        return [c.detail for c in self.components if c.on]

    def describe(self) -> str:
        if not self.available:
            return "market regime unavailable"
        head = f"{self.mode} ({self.score}/5)"
        return head + (": " + "; ".join(self.reasons) if self.reasons else ": all clear")


def _tnx_yield(close: pd.Series) -> pd.Series:
    """^TNX has been quoted both as 42.5 and 4.25 over the years – normalise to percent."""
    return close / 10.0 if close.dropna().median() > 20 else close


def regime_frame(
    market: dict[str, pd.DataFrame],
    hy: Optional[pd.Series] = None,
    p: RegimeParams = RegimeParams(),
) -> pd.DataFrame:
    """Per-date components and score. Used by the live scan and the backtest."""
    spy = market.get(SPY)
    if spy is None or spy.empty:
        return pd.DataFrame()
    idx = spy.index
    out = pd.DataFrame(index=idx)

    def close(sym: str) -> Optional[pd.Series]:
        df = market.get(sym)
        if df is None or df.empty:
            return None
        return df["Close"].reindex(idx).ffill()

    out["spy"] = spy["Close"]
    out["spy_ema"] = ema(spy["Close"], p.ema_span)
    out["c_trend"] = (out["spy"] < out["spy_ema"]) & out["spy_ema"].notna()

    vix, vix3m = close(VIX), close(VIX3M)
    out["vix"] = vix if vix is not None else np.nan
    out["vix_chg"] = (vix / vix.shift(p.vix_lookback) - 1) * 100 if vix is not None else np.nan
    out["c_fear"] = ((out["vix"] > p.vix_max) | (out["vix_chg"] > p.vix_spike_pct)).fillna(False)

    out["vix3m"] = vix3m if vix3m is not None else np.nan
    out["vix_ratio"] = out["vix"] / out["vix3m"]
    out["c_panic"] = (out["vix_ratio"] > 1.0).fillna(False)

    if hy is not None and not hy.dropna().empty:
        h = hy.reindex(idx).ffill()
        out["hy"] = h
        out["hy_chg"] = h - h.shift(p.macro_lookback)
    else:
        out["hy"] = np.nan
        out["hy_chg"] = np.nan
    out["c_credit"] = (out["hy_chg"] > p.credit_bp).fillna(False)

    tnx, brent = close(TNX), close(BRENT)
    if tnx is not None:
        y = _tnx_yield(tnx)
        out["tnx"] = y
        out["tnx_chg"] = y - y.shift(p.macro_lookback)
    else:
        out["tnx"] = np.nan
        out["tnx_chg"] = np.nan
    out["brent"] = brent if brent is not None else np.nan
    out["brent_chg"] = (out["brent"] / out["brent"].shift(p.macro_lookback) - 1) * 100
    out["c_macro"] = ((out["tnx_chg"] > p.yield_bp) | (out["brent_chg"] > p.oil_pct)).fillna(False)

    comps = ["c_trend", "c_fear", "c_panic", "c_credit", "c_macro"]
    out["score"] = out[comps].astype(int).sum(axis=1)
    return out


def assess(market: dict[str, pd.DataFrame], hy: Optional[pd.Series] = None,
           p: RegimeParams = RegimeParams()) -> Regime:
    """Regime as of the latest SPY bar."""
    frame = regime_frame(market, hy, p)
    if frame.empty:
        return Regime(asof=None, available=False, params=p)
    r = frame.iloc[-1]

    def f(x, nd=2, suffix=""):
        return "n/a" if pd.isna(x) else f"{x:.{nd}f}{suffix}"

    comps = [
        Component("trend", "SPY vs 50-day EMA", bool(r.c_trend),
                  f"SPY {f(r.spy)} {'below' if r.c_trend else 'above'} 50 EMA {f(r.spy_ema)}",
                  not pd.isna(r.spy_ema)),
        Component("fear", "VIX level / spike", bool(r.c_fear),
                  f"VIX {f(r.vix, 1)} ({f(r.vix_chg, 0, '%')} in {p.vix_lookback}d)", not pd.isna(r.vix)),
        Component("panic", "VIX term structure", bool(r.c_panic),
                  f"VIX/VIX3M {f(r.vix_ratio)} ({'inverted' if r.c_panic else 'normal'})",
                  not pd.isna(r.vix_ratio)),
        Component("credit", "High-yield credit spread", bool(r.c_credit),
                  f"HY spread {f(r.hy)}% ({'+' if (r.hy_chg or 0) >= 0 else ''}{f(r.hy_chg)} pts in {p.macro_lookback}d)",
                  not pd.isna(r.hy_chg)),
        Component("macro", "10-yr yield / oil momentum", bool(r.c_macro),
                  f"10-yr {f(r.tnx)}% ({'+' if (r.tnx_chg or 0) >= 0 else ''}{f(r.tnx_chg)} in {p.macro_lookback}d), "
                  f"Brent {f(r.brent)} ({'+' if (r.brent_chg or 0) >= 0 else ''}{f(r.brent_chg, 0, '%')})",
                  not (pd.isna(r.tnx_chg) and pd.isna(r.brent_chg))),
    ]
    values = {k: (None if pd.isna(v) else float(v)) for k, v in r.items() if not str(k).startswith("c_")}
    return Regime(asof=frame.index[-1].date(), score=int(r.score), components=comps, params=p, values=values)


def load_inputs(period: str = "2y") -> tuple[dict[str, pd.DataFrame], Optional[pd.Series]]:
    """Download everything the regime needs (network)."""
    from .data import fetch_fred, fetch_history

    return fetch_history(MARKET_SYMBOLS, period=period), fetch_fred(HY_SERIES)
