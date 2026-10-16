"""Signal logic (Tao of Trading style pullback entries, gated).

The old engine added up five criteria and fired at 4/5. Two of those
("ADX >= 20" and "no earnings") were effectively free points for *both*
directions, so a stock without a bullish EMA stack could still score 4/5 and
produce "BUY CALL". Here the logic is layered instead:

GATES (all required; they decide direction)
  1. EMA stack       8 > 21 > 34 > 55 > 89      (PUT: reversed)
  2. Trend           ADX(13) >= 20 and +DI > -DI (PUT: -DI > +DI)
  3. Earnings        none within `earnings_days`
  4. Macro events    no CPI / jobs / FOMC / bellwether earnings today or next session
  5. Market regime   CALLs blocked while the regime score is DEFENSIVE (regime.py)
  6. Sector          CALLs blocked while the stock's sector ETF is extended or
                     breaking down (sector.py)

TRIGGERS (both required for a SIGNAL; one or zero = SETUP, keep watching)
  a. Price within 2% of the 21 EMA (pullback in an uptrend / rally in a downtrend)
  b. Slow stochastic %K <= 40 (PUT: >= 60)

QUALITY (sets confidence only)
  price vs 200 EMA, 20/40/200 stack, 200 EMA slope, RSI in range,
  within 20% of the 52-week high (PUT: low), market regime agreeing (PUT).

Everything is computed for every bar at once, so the backtest replays exactly
the rules the live scanner uses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from . import indicators
from .data import EarningsInfo
from .events import Event, blocking_event
from .levels import Levels, find_levels
from .regime import CAUTION, Regime
from .risk import RiskParams, TradePlan, build_plan
from .sector import SectorState

CONFIDENCE = ("LOW", "MODERATE", "HIGH", "VERY HIGH")

SIGNAL = "SIGNAL"
SETUP = "SETUP"
EARNINGS_BLOCK = "EARNINGS_BLOCK"
REGIME_BLOCK = "REGIME_BLOCK"
EVENT_BLOCK = "EVENT_BLOCK"
SECTOR_BLOCK = "SECTOR_BLOCK"
NO_TREND = "NO_TREND"
NO_DATA = "INSUFFICIENT_DATA"

MIN_BARS = 150  # 89 EMA + ADX warm-up


@dataclass(frozen=True)
class StrategyParams:
    pullback_pct: float = 2.0
    stoch_long_max: float = 40.0
    stoch_short_min: float = 60.0
    adx_min: float = 20.0
    earnings_days: int = 14
    rsi_long: tuple[float, float] = (40.0, 80.0)
    rsi_short: tuple[float, float] = (20.0, 60.0)
    near_extreme_pct: float = 20.0
    use_regime: bool = True


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    kind: str  # "gate" | "trigger" | "quality"


@dataclass
class Signal:
    symbol: str
    asof: Optional[date]
    price: Optional[float]
    direction: Optional[str]  # "CALL" | "PUT" | None
    status: str
    confidence: str = "N/A"
    triggers_met: int = 0
    quality: int = 0
    checks: list[Check] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    values: dict = field(default_factory=dict)
    plan: Optional[TradePlan] = None
    levels: Optional[Levels] = None
    earnings: Optional[EarningsInfo] = None
    regime: Optional[Regime] = None
    event: Optional[Event] = None
    sector: Optional[SectorState] = None

    @property
    def actionable(self) -> bool:
        return self.status == SIGNAL

    @property
    def headline(self) -> str:
        d = self.direction
        if self.status == SIGNAL:
            return f"BUY {d} SIGNAL · {self.confidence} confidence"
        if self.status == SETUP:
            trend = "Uptrend" if d == "CALL" else "Downtrend"
            return f"{trend} – {d} setup forming ({self.triggers_met}/2 entry triggers)"
        if self.status == EARNINGS_BLOCK:
            return f"{d} setup blocked – earnings inside the blackout window"
        if self.status == REGIME_BLOCK:
            return f"{d} setup blocked – market regime is DEFENSIVE"
        if self.status == EVENT_BLOCK:
            when = f" {self.event.day:%a %b %d}" if self.event else ""
            name = self.event.name if self.event else "macro event"
            return f"{d} setup on hold – {name}{when}"
        if self.status == SECTOR_BLOCK:
            etf = self.sector.etf if self.sector else "sector"
            return f"{d} setup blocked – {etf} is extended or breaking down"
        if self.status == NO_DATA:
            return "Not enough price history"
        return "No trend – no trade"


# --------------------------------------------------------------------------- #
# Vectorized rules
# --------------------------------------------------------------------------- #


def criteria(ind: pd.DataFrame, p: StrategyParams = StrategyParams()) -> pd.DataFrame:
    """Boolean table: one row per bar, one column per rule."""
    c = pd.DataFrame(index=ind.index)
    close = ind["Close"]
    e8, e21, e34, e55, e89 = (ind[f"ema_{n}"] for n in (8, 21, 34, 55, 89))

    c["ready"] = ind[["ema_89", "adx", "plus_di", "minus_di", "stoch_k", "atr"]].notna().all(axis=1)

    c["long_stack"] = (e8 > e21) & (e21 > e34) & (e34 > e55) & (e55 > e89)
    c["short_stack"] = (e8 < e21) & (e21 < e34) & (e34 < e55) & (e55 < e89)
    c["long_trend"] = (ind["adx"] >= p.adx_min) & (ind["plus_di"] > ind["minus_di"])
    c["short_trend"] = (ind["adx"] >= p.adx_min) & (ind["minus_di"] > ind["plus_di"])

    c["dist_21_pct"] = (close - e21) / e21 * 100.0
    c["near_21"] = c["dist_21_pct"].abs() <= p.pullback_pct
    c["long_stoch"] = ind["stoch_k"] <= p.stoch_long_max
    c["short_stoch"] = ind["stoch_k"] >= p.stoch_short_min

    lo, hi = p.rsi_long
    c["q_long_200"] = close > ind["ema_200"]
    c["q_long_stack200"] = (ind["ema_20"] > ind["ema_40"]) & (ind["ema_40"] > ind["ema_200"])
    c["q_long_slope"] = ind["ema_200_slope"] > 0
    c["q_long_rsi"] = (ind["rsi"] > lo) & (ind["rsi"] < hi)
    c["q_long_extreme"] = close >= ind["high_52w"] * (1 - p.near_extreme_pct / 100.0)

    lo, hi = p.rsi_short
    c["q_short_200"] = close < ind["ema_200"]
    c["q_short_stack200"] = (ind["ema_20"] < ind["ema_40"]) & (ind["ema_40"] < ind["ema_200"])
    c["q_short_slope"] = ind["ema_200_slope"] < 0
    c["q_short_rsi"] = (ind["rsi"] > lo) & (ind["rsi"] < hi)
    c["q_short_extreme"] = close <= ind["low_52w"] * (1 + p.near_extreme_pct / 100.0)
    return c


LONG_Q = ["q_long_200", "q_long_stack200", "q_long_slope", "q_long_rsi", "q_long_extreme"]
SHORT_Q = ["q_short_200", "q_short_stack200", "q_short_slope", "q_short_rsi", "q_short_extreme"]


def classify(
    c: pd.DataFrame,
    p: StrategyParams = StrategyParams(),
    earnings_block: Optional[pd.Series] = None,
    earnings_unknown: Optional[pd.Series] = None,
    risk_off: Optional[pd.Series] = None,
    event_block: Optional[pd.Series] = None,
    sector_block: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Direction, status and confidence for every bar."""
    idx = c.index

    def _flag(s: Optional[pd.Series]) -> np.ndarray:
        if s is None:
            return np.zeros(len(idx), dtype=bool)
        return s.reindex(idx).fillna(False).astype(bool).to_numpy()

    ready = c["ready"].to_numpy()
    long_dir = c["long_stack"].to_numpy() & c["long_trend"].to_numpy() & ready
    short_dir = c["short_stack"].to_numpy() & c["short_trend"].to_numpy() & ready

    near = c["near_21"].to_numpy().astype(int)
    trig = np.where(long_dir, near + c["long_stoch"].to_numpy().astype(int), 0)
    trig = np.where(short_dir, near + c["short_stoch"].to_numpy().astype(int), trig)

    roff = _flag(risk_off) if p.use_regime else np.zeros(len(idx), dtype=bool)
    q_long = c[LONG_Q].sum(axis=1).to_numpy()
    q_short = c[SHORT_Q].sum(axis=1).to_numpy() + roff.astype(int)
    quality = np.minimum(np.where(long_dir, q_long, np.where(short_dir, q_short, 0)), 5)

    conf = np.select([quality >= 5, quality == 4, quality >= 2], [3, 2, 1], 0)
    conf = np.where(_flag(earnings_unknown), np.maximum(conf - 1, 0), conf)

    status = np.full(len(idx), NO_TREND, dtype=object)
    has_dir = long_dir | short_dir
    status[has_dir] = np.where(trig[has_dir] == 2, SIGNAL, SETUP)
    status[has_dir & _flag(sector_block) & long_dir] = SECTOR_BLOCK
    status[has_dir & roff & long_dir] = REGIME_BLOCK
    status[has_dir & _flag(event_block)] = EVENT_BLOCK
    status[has_dir & _flag(earnings_block)] = EARNINGS_BLOCK
    status[~ready] = NO_DATA

    direction = np.where(long_dir, "CALL", np.where(short_dir, "PUT", None)).astype(object)
    return pd.DataFrame(
        {
            "direction": pd.Series(direction, index=idx, dtype=object),
            "status": status,
            "triggers": trig,
            "quality": quality,
            "confidence": [CONFIDENCE[i] if d else "N/A" for i, d in zip(conf, direction)],
        },
        index=idx,
    )


# --------------------------------------------------------------------------- #
# Live evaluation of the latest bar
# --------------------------------------------------------------------------- #


def _fmt(x: Optional[float], nd: int = 2) -> str:
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.{nd}f}"


def _snapshot(row: pd.Series) -> dict:
    keys = [
        "Close", "ema_8", "ema_21", "ema_34", "ema_55", "ema_89", "ema_20", "ema_40", "ema_200",
        "rsi", "stoch_k", "stoch_d", "adx", "plus_di", "minus_di", "adx_14", "atr", "high_52w", "low_52w",
    ]
    out = {}
    for k in keys:
        v = row.get(k)
        out["price" if k == "Close" else k] = None if v is None or pd.isna(v) else round(float(v), 4)
    return out


def _checks(direction: Optional[str], row: pd.Series, crow: pd.Series, p: StrategyParams,
            earnings: Optional[EarningsInfo], regime: Optional[Regime], today: date,
            event: Optional[Event] = None, sector: Optional[SectorState] = None) -> list[Check]:
    v = _snapshot(row)
    stack = "/".join(_fmt(v[f"ema_{n}"]) for n in (8, 21, 34, 55, 89))
    di = f"ADX {_fmt(v['adx'], 1)}, +DI {_fmt(v['plus_di'], 1)} vs −DI {_fmt(v['minus_di'], 1)}"
    checks: list[Check] = []

    if direction is None:
        checks.append(Check("EMA stack", False,
                            f"8/21/34/55/89 = {stack} (mixed – neither bullish nor bearish)", "gate"))
        trending = bool(crow["long_trend"] or crow["short_trend"])
        checks.append(Check("Trend strength", trending, f"{di} (need ≥ {p.adx_min:g})", "gate"))
        return checks

    long = direction == "CALL"
    checks.append(Check("EMA stack", True,
                        f"8{'>' if long else '<'}21{'>' if long else '<'}34{'>' if long else '<'}55"
                        f"{'>' if long else '<'}89: {stack}", "gate"))
    checks.append(Check("Trend strength", True, f"{di}", "gate"))

    if earnings is not None:
        within = earnings.within(today, p.earnings_days)
        checks.append(Check("Earnings", within is not True,
                            f"{earnings.describe(today)} – blackout {p.earnings_days} days", "gate"))
    checks.append(Check("Macro events", event is None,
                        f"{event.name} on {event.day:%a %b %d} – no new entries the session before or day of"
                        if event else "no CPI / jobs / FOMC / bellwether earnings today or next session", "gate"))
    if regime is not None and regime.available:
        checks.append(Check("Market regime", not (long and regime.risk_off and p.use_regime),
                            regime.describe(), "gate"))
    if long and sector is not None:
        checks.append(Check("Sector", not sector.blocks_calls, sector.detail, "gate"))

    side = "≤" if long else "≥"
    checks.append(Check("Pullback to 21 EMA" if long else "Rally to 21 EMA", bool(crow["near_21"]),
                        f"price {_fmt(v['price'])} is {crow['dist_21_pct']:+.1f}% from 21 EMA "
                        f"{_fmt(v['ema_21'])} (need within {p.pullback_pct:g}%)", "trigger"))
    level = p.stoch_long_max if long else p.stoch_short_min
    checks.append(Check("Stochastic", bool(crow["long_stoch" if long else "short_stoch"]),
                        f"%K {_fmt(v['stoch_k'], 1)} {side} {level:g}", "trigger"))

    pre = "q_long_" if long else "q_short_"
    rlo, rhi = p.rsi_long if long else p.rsi_short
    q_text = {
        "200": f"price {'above' if long else 'below'} 200 EMA {_fmt(v['ema_200'])}",
        "stack200": f"20/40/200 EMAs {'rising' if long else 'falling'} in order",
        "slope": f"200 EMA {'rising' if long else 'falling'}",
        "rsi": f"RSI {_fmt(v['rsi'], 1)} in {rlo:g}–{rhi:g}",
        "extreme": (f"within {p.near_extreme_pct:g}% of 52w high {_fmt(v['high_52w'])}" if long
                    else f"within {p.near_extreme_pct:g}% of 52w low {_fmt(v['low_52w'])}"),
    }
    for key, text in q_text.items():
        checks.append(Check(text, bool(crow[pre + key]), "", "quality"))
    if not long and regime is not None and regime.available:
        checks.append(Check("market regime DEFENSIVE (supports puts)", regime.risk_off, "", "quality"))
    return checks


def evaluate(
    symbol: str,
    df: pd.DataFrame,
    p: StrategyParams = StrategyParams(),
    earnings: Optional[EarningsInfo] = None,
    regime: Optional[Regime] = None,
    risk: RiskParams = RiskParams(),
    account_size: Optional[float] = None,
    risk_pct: float = 1.0,
    today: Optional[date] = None,
    partial_bar: bool = False,
    events: Optional[list[Event]] = None,
    sector: Optional[SectorState] = None,
) -> Signal:
    """Evaluate the most recent bar of `df` (daily OHLCV)."""
    symbol = symbol.upper()
    today = today or date.today()
    if df is None or len(df) < MIN_BARS:
        return Signal(symbol, None, None, None, NO_DATA,
                      warnings=[f"need at least {MIN_BARS} daily bars, have {0 if df is None else len(df)}"])

    ind = indicators.compute(df)
    c = criteria(ind, p)
    last_idx = ind.index[-1]

    def _last(value: Optional[bool]) -> Optional[pd.Series]:
        if value is None:
            return None
        s = pd.Series(False, index=ind.index)
        s.iloc[-1] = bool(value)
        return s

    e_within = earnings.within(today, p.earnings_days) if earnings else None
    event = blocking_event(events or [], today, symbol, sector.etf if sector else None)
    cls = classify(
        c, p,
        earnings_block=_last(e_within is True),
        earnings_unknown=_last(earnings is not None and earnings.status == "unknown"),
        risk_off=_last(regime.risk_off if (regime and regime.available) else False),
        event_block=_last(event is not None),
        sector_block=_last(sector is not None and sector.blocks_calls),
    ).iloc[-1]

    row, crow = ind.iloc[-1], c.iloc[-1]
    direction = cls["direction"] if isinstance(cls["direction"], str) else None
    sig = Signal(
        symbol=symbol,
        asof=last_idx.date(),
        price=float(row["Close"]),
        direction=direction,
        status=str(cls["status"]),
        confidence=str(cls["confidence"]),
        triggers_met=int(cls["triggers"]),
        quality=int(cls["quality"]),
        values=_snapshot(row),
        earnings=earnings,
        regime=regime,
        event=event,
        sector=sector,
    )
    sig.checks = _checks(direction, row, crow, p, earnings, regime, today, event, sector)
    sig.levels = find_levels(df)

    if partial_bar:
        sig.warnings.append("intraday: today's bar is not closed yet, the signal can change by the close")
    if earnings is not None and earnings.status == "unknown":
        sig.warnings.append("earnings date could not be checked – confidence reduced one level")
    if pd.isna(row.get("ema_200")):
        sig.warnings.append("less than 200 bars of history – 200 EMA checks unavailable")
    if regime is not None and not regime.available:
        sig.warnings.append("market regime data unavailable – regime gate skipped")

    if regime is not None and regime.available and regime.mode == CAUTION and direction == "CALL":
        sig.warnings.append(f"market regime CAUTION ({regime.score}/5) – half size")

    if sig.status == SIGNAL:
        mult = regime.size_multiplier if (regime is not None and regime.available and direction == "CALL") else 1.0
        sig.plan = build_plan(ind, direction, risk, sig.levels, account_size, risk_pct * max(mult, 0.0))
        if mult < 1.0 and sig.plan.risk_dollars is not None:
            sig.plan.notes.append(f"position size cut to {mult:.0%} by market regime")
    return sig
