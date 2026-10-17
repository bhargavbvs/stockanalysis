"""Support / resistance from clustered swing pivots."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Levels:
    price: float
    resistance: list[float] = field(default_factory=list)  # nearest first, ascending
    support: list[float] = field(default_factory=list)  # nearest first, descending
    high_52w: float | None = None
    low_52w: float | None = None


def _cluster(values: list[float], tol: float) -> list[float]:
    if not values:
        return []
    values = sorted(values)
    clusters: list[list[float]] = [[values[0]]]
    for v in values[1:]:
        center = float(np.mean(clusters[-1]))
        if abs(v - center) / center <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [float(np.mean(c)) for c in clusters]


def find_levels(df: pd.DataFrame, lookback: int = 120, window: int = 5, tol: float = 0.015, n: int = 3) -> Levels:
    """Swing highs/lows over `lookback` bars, clustered within `tol`.

    Only confirmed pivots count (a pivot needs `window` bars on both sides).
    Highs and lows are pooled: an old swing low above today's price acts as
    resistance, and vice versa.
    """
    recent = df.tail(lookback)
    price = float(df["Close"].iloc[-1])
    span = 2 * window + 1
    is_high = recent["High"] == recent["High"].rolling(span, center=True).max()
    is_low = recent["Low"] == recent["Low"].rolling(span, center=True).min()
    pivots = list(recent["High"][is_high]) + list(recent["Low"][is_low])
    levels = _cluster([float(x) for x in pivots], tol)

    year = df.tail(252)
    return Levels(
        price=price,
        resistance=sorted(l for l in levels if l > price * 1.001)[:n],
        support=sorted((l for l in levels if l < price * 0.999), reverse=True)[:n],
        high_52w=float(year["High"].max()),
        low_52w=float(year["Low"].min()),
    )
