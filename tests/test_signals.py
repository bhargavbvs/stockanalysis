from datetime import timedelta

import pandas as pd
import pytest

from conftest import choppy, make_ohlc
from stockbot import regime as rg
from stockbot.data import EarningsInfo
from stockbot.events import Event
from stockbot.sector import SectorState
from stockbot.signals import (
    EARNINGS_BLOCK, EVENT_BLOCK, NO_DATA, NO_TREND, REGIME_BLOCK, SECTOR_BLOCK, SETUP, SIGNAL, evaluate,
)

NONE = EarningsInfo("none")


def today(df):
    return df.index[-1].date()


def test_uptrend_pullback_is_call_signal(up_df):
    s = evaluate("T", up_df, earnings=NONE, today=today(up_df))
    assert (s.status, s.direction) == (SIGNAL, "CALL")
    assert s.plan.stop < s.plan.entry < s.plan.target


def test_downtrend_rally_is_put_signal(down_df):
    s = evaluate("T", down_df, earnings=NONE, today=today(down_df))
    assert (s.status, s.direction) == (SIGNAL, "PUT")
    assert s.plan.target < s.plan.entry < s.plan.stop


@pytest.mark.parametrize("seed", range(30))
def test_never_calls_in_a_steady_downtrend(seed):
    """Regression: the old 5-point score said BUY CALL on 10/40 of these."""
    df = make_ohlc([-0.0015] * 420, start=200, seed=seed, noise=0.006)
    s = evaluate("T", df, earnings=NONE, today=today(df))
    assert s.direction != "CALL"


def test_choppy_market_has_no_trend():
    s = evaluate("T", choppy(seed=0), earnings=NONE)
    assert s.status == NO_TREND and s.direction is None
    assert s.plan is None


def test_short_history_is_flagged():
    s = evaluate("T", make_ohlc([0.001] * 50))
    assert s.status == NO_DATA


def test_earnings_inside_blackout_blocks(up_df):
    t = today(up_df)
    s = evaluate("T", up_df, earnings=EarningsInfo("known", t + timedelta(days=5)), today=t)
    assert s.status == EARNINGS_BLOCK and s.plan is None


def test_earnings_outside_blackout_ok(up_df):
    t = today(up_df)
    s = evaluate("T", up_df, earnings=EarningsInfo("known", t + timedelta(days=30)), today=t)
    assert s.status == SIGNAL


def test_unknown_earnings_lowers_confidence(up_df):
    t = today(up_df)
    known = evaluate("T", up_df, earnings=NONE, today=t)
    unknown = evaluate("T", up_df, earnings=EarningsInfo("unknown"), today=t)
    assert unknown.status == SIGNAL
    order = ["LOW", "MODERATE", "HIGH", "VERY HIGH"]
    assert order.index(unknown.confidence) == order.index(known.confidence) - 1
    assert any("earnings date could not be checked" in w for w in unknown.warnings)


def test_macro_event_tomorrow_blocks(up_df):
    t = today(up_df)
    nxt = (pd.Timestamp(t) + pd.offsets.BDay(1)).date()
    s = evaluate("T", up_df, earnings=NONE, today=t, events=[Event(nxt, "CPI")])
    assert s.status == EVENT_BLOCK and "CPI" in s.headline


def test_sector_scoped_event_only_hits_that_sector(up_df):
    t = today(up_df)
    e = [Event(t, "NVDA earnings", ("SOXX", "NVDA"))]
    tech = SectorState("XLK", False, False, 55.0, 3.0, "XLK fine")
    semi = SectorState("SOXX", False, False, 55.0, 3.0, "SOXX fine")
    assert evaluate("T", up_df, earnings=NONE, today=t, events=e, sector=tech).status == SIGNAL
    assert evaluate("T", up_df, earnings=NONE, today=t, events=e, sector=semi).status == EVENT_BLOCK


def test_extended_sector_blocks_calls(up_df):
    hot = SectorState("SOXX", True, False, 80.0, 35.0, "SOXX RSI 80, +35% vs 50-day, EXTENDED")
    s = evaluate("T", up_df, earnings=NONE, today=today(up_df), sector=hot)
    assert s.status == SECTOR_BLOCK


def _regime(score: int) -> rg.Regime:
    comps = [rg.Component(str(i), str(i), i < score, f"c{i}") for i in range(5)]
    return rg.Regime(asof=None, score=score, components=comps)


def test_defensive_regime_blocks_calls_but_not_puts(up_df, down_df):
    r = _regime(3)
    assert evaluate("T", up_df, earnings=NONE, today=today(up_df), regime=r).status == REGIME_BLOCK
    assert evaluate("T", down_df, earnings=NONE, today=today(down_df), regime=r).status == SIGNAL


def test_caution_regime_halves_size(up_df):
    t = today(up_df)
    full = evaluate("T", up_df, earnings=NONE, today=t, regime=_regime(0), account_size=100_000)
    half = evaluate("T", up_df, earnings=NONE, today=t, regime=_regime(2), account_size=100_000)
    assert half.status == SIGNAL
    assert half.plan.risk_dollars == pytest.approx(full.plan.risk_dollars / 2)
    assert any("half size" in w for w in half.warnings)


def test_regime_filter_can_be_disabled(up_df):
    from stockbot.signals import StrategyParams

    s = evaluate("T", up_df, StrategyParams(use_regime=False), earnings=NONE, today=today(up_df), regime=_regime(5))
    assert s.status == SIGNAL


def test_setup_when_only_one_trigger():
    # uptrend, shallow 1-day dip: near the 21 EMA? no; stochastic still high -> trend but no entry
    df = make_ohlc([0.004] * 400)
    s = evaluate("T", df, earnings=NONE, today=today(df))
    assert s.status == SETUP and s.direction == "CALL" and s.plan is None


def test_checks_explain_the_decision(up_df):
    s = evaluate("T", up_df, earnings=NONE, today=today(up_df))
    names = [c.name for c in s.checks]
    assert {"EMA stack", "Trend strength", "Earnings", "Macro events", "Stochastic"} <= set(names)
    assert all(c.passed for c in s.checks if c.kind in ("gate", "trigger"))
