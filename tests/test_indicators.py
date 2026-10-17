import numpy as np
import pandas as pd

from conftest import make_ohlc
from stockbot import indicators as ind


def test_ema_matches_pandas_reference():
    s = pd.Series(np.linspace(1, 50, 120))
    out = ind.ema(s, 21)
    ref = s.ewm(span=21, adjust=False).mean()
    assert out.iloc[:20].isna().all()
    assert np.allclose(out.iloc[20:], ref.iloc[20:])


def test_rsi_extremes_and_flat():
    up = pd.Series(np.arange(1, 60, dtype=float))
    down = up[::-1].reset_index(drop=True)
    flat = pd.Series(np.full(60, 10.0))
    assert ind.rsi(up).iloc[-1] == 100.0
    assert ind.rsi(down).iloc[-1] == 0.0
    assert ind.rsi(flat).iloc[-1] == 50.0
    assert ind.rsi(up).iloc[:14].isna().all()


def test_stochastic_bounds_and_zero_range():
    df = make_ohlc([0.01] * 40)
    k = ind.stochastic(df)["stoch_k"].dropna()
    assert ((k >= 0) & (k <= 100)).all()
    assert k.iloc[-1] > 80  # closing near the highs of a rally

    idx = pd.bdate_range("2024-01-01", periods=30)
    flat = pd.DataFrame({"Open": 5.0, "High": 5.0, "Low": 5.0, "Close": 5.0}, index=idx)
    assert ind.stochastic(flat)["stoch_k"].iloc[-1] == 50.0


def test_atr_constant_range():
    idx = pd.bdate_range("2024-01-01", periods=60)
    df = pd.DataFrame({"Open": 10.0, "High": 11.0, "Low": 9.0, "Close": 10.0}, index=idx)
    assert abs(ind.atr(df).iloc[-1] - 2.0) < 1e-9


def test_adx_direction():
    up = ind.adx(make_ohlc([0.006] * 200, noise=0.002))
    down = ind.adx(make_ohlc([-0.006] * 200, noise=0.002))
    assert up["adx"].iloc[-1] > 25 and up["plus_di"].iloc[-1] > up["minus_di"].iloc[-1]
    assert down["adx"].iloc[-1] > 25 and down["minus_di"].iloc[-1] > down["plus_di"].iloc[-1]


def test_compute_adds_all_columns():
    out = ind.compute(make_ohlc([0.001] * 300))
    for col in ["ema_8", "ema_21", "ema_89", "ema_200", "rsi", "stoch_k", "adx", "plus_di", "atr",
                "high_52w", "low_52w", "ema_200_slope"]:
        assert col in out
    assert out["ema_200"].notna().iloc[-1]
