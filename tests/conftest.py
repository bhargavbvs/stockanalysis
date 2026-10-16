"""Synthetic price data so the test suite never touches the network."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_ohlc(returns, start: float = 100.0, seed: int = 0, noise: float = 0.004,
              start_date: str = "2022-01-03") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r = np.asarray(returns, dtype=float) + rng.normal(0, noise, len(returns))
    close = start * np.exp(np.cumsum(r))
    open_ = np.r_[start, close[:-1]]
    spread = np.abs(rng.normal(0, 0.006, len(r))) + 0.003
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    idx = pd.bdate_range(start_date, periods=len(r))
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 1e6}, index=idx)


def uptrend_pullback(n: int = 400, seed: int = 0) -> pd.DataFrame:
    """Steady uptrend, then a 4-day dip into the 21 EMA."""
    return make_ohlc([0.004] * n + [-0.006] * 4, seed=seed)


def downtrend_rally(n: int = 400, seed: int = 0) -> pd.DataFrame:
    """Steady downtrend, then a 4-day bounce into the 21 EMA."""
    return make_ohlc([-0.004] * n + [0.006] * 4, start=300.0, seed=seed)


def choppy(n: int = 400, seed: int = 0) -> pd.DataFrame:
    return make_ohlc(np.sin(np.arange(n) / 6) * 0.01, seed=seed, noise=0.01)


def constant(level: float, index: pd.DatetimeIndex) -> pd.DataFrame:
    s = pd.Series(level, index=index, dtype=float)
    return pd.DataFrame({"Open": s, "High": s * 1.001, "Low": s * 0.999, "Close": s, "Volume": 0.0})


def calm_market(index: pd.DatetimeIndex, spy_up: bool = True) -> dict[str, pd.DataFrame]:
    n = len(index)
    spy = make_ohlc([0.0008 if spy_up else -0.0015] * n, start=500, seed=7, noise=0.002,
                    start_date=str(index[0].date()))
    spy.index = index
    return {"SPY": spy, "^VIX": constant(15.0, index), "^VIX3M": constant(18.0, index),
            "^TNX": constant(4.2, index), "BZ=F": constant(75.0, index)}


@pytest.fixture
def up_df():
    return uptrend_pullback()


@pytest.fixture
def down_df():
    return downtrend_rally()
