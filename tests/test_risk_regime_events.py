from datetime import date

import numpy as np
import pandas as pd
import pytest

from conftest import calm_market, constant, make_ohlc
from stockbot import indicators, regime as rg
from stockbot.events import Event, block_series, blocking_event, load_calendar, next_session
from stockbot.risk import RiskParams, build_plan
from stockbot.sector import assess as sector_assess


# ----------------------------------------------------------------- risk
@pytest.mark.parametrize("seed", range(25))
def test_call_stop_always_below_entry_put_stop_above(seed):
    """Regression: the old max(support, 21 EMA) stop sat above entry on 34/39 pullbacks."""
    df = make_ohlc([0.003] * 300 + [-0.008] * 5, seed=seed)
    ind = indicators.compute(df)
    atr = ind["atr"].iloc[-1]
    call = build_plan(ind, "CALL")
    put = build_plan(ind, "PUT")
    assert call.stop < call.entry and put.stop > put.entry
    for plan in (call, put):
        assert 1.0 * atr - 1e-9 <= plan.risk_per_share <= 3.0 * atr + 1e-9
        assert plan.targets[1][1] == pytest.approx(plan.target)


def test_position_size_from_account_risk():
    ind = indicators.compute(make_ohlc([0.003] * 300))
    plan = build_plan(ind, "CALL", RiskParams(), account_size=50_000, risk_pct=1.0)
    assert plan.risk_dollars == 500
    assert plan.shares == int(500 // plan.risk_per_share)


# ----------------------------------------------------------------- regime
def _market(n=260, **overrides):
    idx = pd.bdate_range("2025-01-01", periods=n)
    m = calm_market(idx)
    m.update(overrides)
    return m, idx


def test_calm_market_scores_zero():
    m, idx = _market()
    r = rg.assess(m, pd.Series(3.0, index=idx))
    assert r.score == 0 and r.mode == rg.NORMAL and not r.risk_off and r.size_multiplier == 1.0


def test_credit_and_trend_make_caution():
    idx = pd.bdate_range("2025-01-01", periods=260)
    m = calm_market(idx, spy_up=False)
    hy = pd.Series(np.r_[np.full(230, 3.0), np.linspace(3.0, 3.6, 30)], index=idx)
    r = rg.assess(m, hy)
    on = {c.key for c in r.components if c.on}
    assert on == {"trend", "credit"} and r.mode == rg.CAUTION and r.size_multiplier == 0.5


def test_panic_is_defensive():
    idx = pd.bdate_range("2025-01-01", periods=260)
    m = calm_market(idx, spy_up=False)
    m["^VIX"] = constant(32.0, idx)
    m["^VIX3M"] = constant(26.0, idx)
    r = rg.assess(m)
    assert r.score >= 3 and r.risk_off
    assert "credit" in [c.key for c in r.components if not c.available]


def test_hy_spread_is_lagged_one_session():
    idx = pd.bdate_range("2025-01-01", periods=260)
    m = calm_market(idx)
    hy = pd.Series(3.0, index=idx)
    hy.iloc[-1] = 9.0  # today's print isn't published until tomorrow
    r = rg.assess(m, hy)
    assert r.values["hy"] == pytest.approx(3.0)


def test_old_style_tnx_quotes_are_normalised():
    idx = pd.bdate_range("2025-01-01", periods=260)
    m = calm_market(idx)
    m["^TNX"] = pd.DataFrame({"Close": np.r_[np.full(240, 42.0), np.linspace(42.0, 46.0, 20)]}, index=idx)
    r = rg.assess(m)
    assert r.values["tnx"] == pytest.approx(4.6)
    assert next(c for c in r.components if c.key == "macro").on  # +0.4 pts in 20 days


def test_missing_market_data_is_unavailable():
    r = rg.assess({})
    assert not r.available and not r.risk_off


# ----------------------------------------------------------------- events
def test_calendar_file_parses(tmp_path):
    f = tmp_path / "events.yaml"
    f.write_text("events:\n  - {date: 2026-11-10, name: CPI, scope: market}\n"
                 "  - {date: 2026-11-18, name: NVDA earnings, scope: [SOXX, NVDA]}\n"
                 "bellwethers:\n  SOXX: [nvda, tsm]\n")
    events, bell = load_calendar(f)
    assert [e.name for e in events] == ["CPI", "NVDA earnings"]
    assert bell == {"SOXX": ["NVDA", "TSM"]}


def test_repo_calendar_is_valid():
    events, bell = load_calendar("events.yaml")
    assert len(events) >= 10 and "SOXX" in bell


def test_veto_window_is_session_before_and_day_of():
    cpi = Event(date(2026, 11, 10), "CPI")  # Tuesday
    assert blocking_event([cpi], date(2026, 11, 9), "AAPL")  # Monday
    assert blocking_event([cpi], date(2026, 11, 10), "AAPL")
    assert not blocking_event([cpi], date(2026, 11, 6), "AAPL")  # Friday before
    assert not blocking_event([cpi], date(2026, 11, 11), "AAPL")
    monday = Event(date(2026, 11, 9), "Jobs")
    assert next_session(date(2026, 11, 6)) == date(2026, 11, 9)
    assert blocking_event([monday], date(2026, 11, 6), "AAPL")  # Friday before a Monday event
    # Holiday: Fri Jan 15 2027 -> next session is Tue Jan 19 (MLK day Mon Jan 18)
    tue = Event(date(2027, 1, 19), "Something")
    assert next_session(date(2027, 1, 15)) == date(2027, 1, 19)
    assert blocking_event([tue], date(2027, 1, 15), "AAPL")


def test_calendar_runs_out_warning():
    from stockbot.events import calendar_runs_out

    evs = [Event(date(2027, 4, 28), "FOMC")]
    assert calendar_runs_out(evs, date(2026, 10, 16)) is None
    assert calendar_runs_out(evs, date(2027, 4, 1)) == date(2027, 4, 28)


def test_block_series_matches_live_rule():
    idx = pd.bdate_range("2026-11-02", "2026-11-13")
    flags = block_series([Event(date(2026, 11, 10), "CPI")], idx, "AAPL")
    assert list(flags[flags].index.date) == [date(2026, 11, 9), date(2026, 11, 10)]
    scoped = block_series([Event(date(2026, 11, 10), "NVDA earnings", ("SOXX",))], idx, "AAPL", "XLK")
    assert not scoped.any()


# ----------------------------------------------------------------- sector
def test_sector_extension_and_breakdown():
    hot = make_ohlc([0.012] * 120, noise=0.001)
    st = sector_assess("SOXX", hot)
    assert st.extended and st.blocks_calls
    cold = make_ohlc([0.002] * 120 + [-0.01] * 6, noise=0.001)
    st2 = sector_assess("SOXX", cold)
    assert st2.breaking and st2.blocks_calls
    calm = make_ohlc([0.0005] * 150, noise=0.004, seed=3)
    assert not sector_assess("XLK", calm).extended
