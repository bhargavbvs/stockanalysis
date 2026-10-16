from datetime import date

import pandas as pd
import pytest

from conftest import make_ohlc
from stockbot.backtest import VARIANTS, earnings_block_series, forward_edge, run, simulate, summarize
from stockbot.risk import RiskParams
from stockbot.signals import SIGNAL, StrategyParams


def saw_uptrend(cycles=12, seed=1):
    """Uptrend with regular pullbacks -> several CALL signals."""
    r = []
    for _ in range(cycles):
        r += [0.006] * 25 + [-0.007] * 5
    return make_ohlc([0.002] * 150 + r, seed=seed, noise=0.003)


def _cls(index, signal_at, direction="CALL"):
    cls = pd.DataFrame({"status": "NO_TREND", "direction": None, "confidence": "N/A"}, index=index)
    cls["direction"] = cls["direction"].astype(object)
    for i in signal_at:
        cls.iloc[i, cls.columns.get_loc("status")] = SIGNAL
        cls.iloc[i, cls.columns.get_loc("direction")] = direction
        cls.iloc[i, cls.columns.get_loc("confidence")] = "HIGH"
    return cls


def _bars(rows):
    idx = pd.bdate_range("2024-01-01", periods=len(rows))
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)
    df["atr"] = 1.0
    return df


def test_entry_is_next_open_and_stop_wins_ties():
    rows = [(100, 101, 99, 100)] * 12 + [
        (100, 100.5, 99.5, 100),   # i = 12: signal bar
        (101, 101, 101, 101),      # entry at this open (101), no hit
        (101, 110, 90, 100),       # touches stop AND target -> stop first
    ] + [(100, 101, 99, 100)] * 5
    df = _bars(rows)
    rp = RiskParams(swing_lookback=3, min_atr=1.0, max_atr=3.0, target_r=2.0)
    trades = simulate("X", df, _cls(df.index, [12]), rp)
    assert len(trades) == 1
    t = trades[0]
    assert t.entry_date == df.index[13] and t.entry == 101
    assert t.reason == "stop" and t.r == pytest.approx(-1.0)


def test_gap_through_stop_fills_at_open():
    rows = [(100, 101, 99, 100)] * 13 + [(100, 100, 100, 100), (95, 96, 94, 95)] + [(95, 96, 94, 95)] * 3
    df = _bars(rows)
    t = simulate("X", df, _cls(df.index, [12]), RiskParams(swing_lookback=3))[0]
    assert t.reason == "stop" and t.exit == 95 and t.r < -1


def test_time_stop_and_one_position_at_a_time():
    rows = [(100, 100.2, 99.8, 100)] * 60
    df = _bars(rows)
    rp = RiskParams(max_hold_bars=5)
    trades = simulate("X", df, _cls(df.index, [20, 21, 22, 30]), rp)
    assert [t.reason for t in trades] == ["time", "time"]
    assert trades[0].bars == 5 and trades[1].signal_date == df.index[30]


def test_put_target():
    rows = [(100, 101, 99, 100)] * 13 + [(100, 100, 100, 100), (99, 99.5, 90, 92)] + [(92, 93, 91, 92)] * 3
    df = _bars(rows)
    t = simulate("X", df, _cls(df.index, [12], "PUT"), RiskParams(swing_lookback=3))[0]
    assert t.reason == "target" and t.r == pytest.approx(2.0)


def test_earnings_block_series():
    idx = pd.bdate_range("2026-01-01", "2026-03-31")
    s = earnings_block_series(idx, [date(2026, 2, 10)], days=14)
    blocked = s[s].index
    assert blocked.min() == pd.Timestamp("2026-01-27") and blocked.max() == pd.Timestamp("2026-02-10")
    assert not earnings_block_series(idx, None, 14).any()


def test_full_run_and_variants():
    hist = {"UP": saw_uptrend(), "UP2": saw_uptrend(seed=5)}
    sp, rp = StrategyParams(), RiskParams()
    core = run(hist, sp, rp, VARIANTS[0])
    assert core and all(t.direction == "CALL" for t in core)
    assert all(t.entry_date > t.signal_date for t in core)
    # an earnings date right on top of every signal removes them
    eds = {sym: [t.signal_date.date() for t in core if t.symbol == sym] for sym in hist}
    vetoed = run(hist, sp, rp, VARIANTS[1], earnings=eds)
    assert len(vetoed) < len(core)
    s = summarize(core)
    assert s["trades"] == len(core) and -1.5 < s["avg_r"] < 3.5
    assert forward_edge(hist, core)["signals"] is not None
