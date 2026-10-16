"""Trade plan: ATR/structure stop, R-multiple targets, position size.

The old code set the CALL stop at max(nearest support, 21 EMA). When price sat
just *below* the 21 EMA (which the pullback rule allows) that put the stop
above the entry and the risk/reward came out as 1:0. Here the stop is always
on the correct side of the entry by construction:

    long stop  = entry - clamp(entry - (swing_low  - 0.25*ATR), 1*ATR, 3*ATR)
    short stop = entry + clamp((swing_high + 0.25*ATR) - entry, 1*ATR, 3*ATR)

The backtest simulates exactly this stop and the 2R target, so the plan the
bot sends is the plan that was tested.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .levels import Levels


@dataclass(frozen=True)
class RiskParams:
    swing_lookback: int = 10
    atr_buffer: float = 0.25
    min_atr: float = 1.0
    max_atr: float = 3.0
    target_r: float = 2.0
    max_hold_bars: int = 20


@dataclass
class TradePlan:
    direction: str  # "CALL" | "PUT"
    entry: float
    stop: float
    atr: float
    stop_basis: str
    targets: list[tuple[float, float]]  # (R multiple, price)
    target_r: float
    max_hold_bars: int
    nearest_level: Optional[float] = None
    r_to_level: Optional[float] = None
    shares: Optional[int] = None
    risk_dollars: Optional[float] = None
    notes: list[str] = field(default_factory=list)

    @property
    def risk_per_share(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def stop_pct(self) -> float:
        return (self.stop - self.entry) / self.entry * 100.0

    @property
    def target(self) -> float:
        sign = 1 if self.direction == "CALL" else -1
        return self.entry + sign * self.target_r * self.risk_per_share


def stop_distance(entry: float, swing: float, atr: float, direction: str, p: RiskParams) -> tuple[float, str]:
    """Distance from entry to stop, and a human-readable reason."""
    if direction == "CALL":
        structural = entry - (swing - p.atr_buffer * atr)
        label = f"{p.swing_lookback}-day swing low {swing:.2f}"
    else:
        structural = (swing + p.atr_buffer * atr) - entry
        label = f"{p.swing_lookback}-day swing high {swing:.2f}"
    lo, hi = p.min_atr * atr, p.max_atr * atr
    if structural < lo:
        return lo, f"{p.min_atr:g} ATR minimum (swing too close)"
    if structural > hi:
        return hi, f"capped at {p.max_atr:g} ATR (swing too far)"
    return structural, f"beyond {label}"


def build_plan(
    ind: pd.DataFrame,
    direction: str,
    p: RiskParams = RiskParams(),
    levels: Optional[Levels] = None,
    account_size: Optional[float] = None,
    risk_pct: float = 1.0,
) -> TradePlan:
    last = ind.iloc[-1]
    entry = float(last["Close"])
    atr = float(last["atr"])
    window = ind.tail(p.swing_lookback)
    swing = float(window["Low"].min() if direction == "CALL" else window["High"].max())

    dist, basis = stop_distance(entry, swing, atr, direction, p)
    sign = 1 if direction == "CALL" else -1
    stop = entry - sign * dist
    targets = [(r, entry + sign * r * dist) for r in (1.0, 2.0, 3.0)]

    plan = TradePlan(
        direction=direction,
        entry=entry,
        stop=stop,
        atr=atr,
        stop_basis=basis,
        targets=targets,
        target_r=p.target_r,
        max_hold_bars=p.max_hold_bars,
    )

    if levels is not None:
        lvl = (levels.resistance if direction == "CALL" else levels.support) or []
        if lvl:
            plan.nearest_level = lvl[0]
            plan.r_to_level = abs(lvl[0] - entry) / dist
            if plan.r_to_level < p.target_r:
                kind = "Resistance" if direction == "CALL" else "Support"
                plan.notes.append(f"{kind} at {lvl[0]:.2f} is only {plan.r_to_level:.1f}R away")

    if account_size and account_size > 0:
        plan.risk_dollars = account_size * risk_pct / 100.0
        plan.shares = max(0, math.floor(plan.risk_dollars / dist))

    return plan
