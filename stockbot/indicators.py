"""Technical indicators.

Every function takes a full price history and returns a full Series/DataFrame
(one value per bar), so the same code drives live scans and the backtest.
Smoothing follows Wilder's definitions (RSI, ATR, ADX), which is what most
charting platforms show.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FIB_EMAS = (5, 8, 13, 21, 34, 55, 89)
TREND_EMAS = (20, 40, 200)


def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average. NaN until `span` bars are available."""
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def wilder(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (an EMA with alpha = 1/period)."""
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index with Wilder smoothing."""
    delta = close.diff()
    gain = wilder(delta.clip(lower=0.0), period)
    loss = wilder((-delta).clip(lower=0.0), period)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = gain / loss
        out = 100.0 - 100.0 / (1.0 + rs)
    # No losses -> 100, no gains -> 0, no movement at all -> 50.
    out = out.where(loss != 0, 100.0)
    out = out.where(~((gain == 0) & (loss == 0)), 50.0)
    out[gain.isna() | loss.isna()] = np.nan
    return out


def stochastic(df: pd.DataFrame, k_period: int = 8, k_smooth: int = 3, d_period: int = 3) -> pd.DataFrame:
    """Slow stochastic (%K smoothed by `k_smooth`, %D = SMA of slow %K).

    A bar range of zero (flat market) yields a neutral 50 instead of a
    division-by-zero NaN/inf.
    """
    low_min = df["Low"].rolling(k_period).min()
    high_max = df["High"].rolling(k_period).max()
    rng = high_max - low_min
    fast_k = 100.0 * (df["Close"] - low_min) / rng.replace(0, np.nan)
    fast_k = fast_k.where(rng != 0, 50.0)
    fast_k[low_min.isna()] = np.nan
    slow_k = fast_k.rolling(k_smooth).mean()
    slow_d = slow_k.rolling(d_period).mean()
    return pd.DataFrame({"stoch_k": slow_k, "stoch_d": slow_d})


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["Close"].shift()
    return pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev_close).abs(), (df["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder)."""
    return wilder(true_range(df), period)


def adx(df: pd.DataFrame, period: int = 13) -> pd.DataFrame:
    """ADX plus the directional indicators.

    ADX alone measures trend *strength* in either direction. The signal logic
    also needs *direction* (+DI vs -DI), otherwise a strong downtrend would
    count as "trend confirmed" for a call.
    """
    up = df["High"].diff()
    down = -df["Low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)

    tr_s = wilder(true_range(df), period)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * wilder(plus_dm, period) / tr_s
        minus_di = 100.0 * wilder(minus_dm, period) / tr_s
        di_sum = plus_di + minus_di
        dx = 100.0 * (plus_di - minus_di).abs() / di_sum.replace(0, np.nan)
    dx = dx.fillna(0.0).where(di_sum.notna())
    return pd.DataFrame(
        {"adx": wilder(dx, period), "plus_di": plus_di, "minus_di": minus_di},
        index=df.index,
    )


def compute(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of `df` (OHLCV) with every indicator the strategy uses."""
    out = df.copy()
    close = out["Close"]
    for span in FIB_EMAS + TREND_EMAS:
        out[f"ema_{span}"] = ema(close, span)

    out["rsi"] = rsi(close, 14)
    out = out.join(stochastic(out, 8, 3, 3))

    a13 = adx(out, 13)
    out["adx"] = a13["adx"]
    out["plus_di"] = a13["plus_di"]
    out["minus_di"] = a13["minus_di"]
    out["adx_14"] = adx(out, 14)["adx"]

    out["atr"] = atr(out, 14)
    out["high_52w"] = out["High"].rolling(252, min_periods=20).max()
    out["low_52w"] = out["Low"].rolling(252, min_periods=20).min()
    out["ema_200_slope"] = out["ema_200"] - out["ema_200"].shift(5)
    if "Volume" in out:
        out["vol_avg20"] = out["Volume"].rolling(20).mean()
    return out
