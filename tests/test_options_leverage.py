"""Leveraged-ETF math, option positions, and the two-message brief."""

import math
import types
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from conftest import calm_market, choppy, downtrend_rally, make_ohlc, uptrend_pullback
from stockbot import brief, config, data, leverage as lev, options as opt, scanner, sector
from stockbot.data import EarningsInfo, Fundamentals
from stockbot.tracker import Tracker

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")
TODAY = date(2026, 10, 16)


# ------------------------------------------------------------------ config
def test_parse_options_and_errors():
    o = opt.parse_options("apld:2027-01-15:25C:20@6.897, INTC:2027-06-17:100c:1@25, TSLA:2026-12-18:300P:2")
    assert o[0] == opt.OptionHolding("APLD", date(2027, 1, 15), 25.0, "C", 20.0, 6.897)
    assert o[1].right == "C" and o[2].right == "P" and o[2].cost is None
    assert o[0].label == "APLD $25 call Jan 15 '27"
    for bad in ("APLD:2027-01-15:25:20@1", "APLD:Jan15:25C:20", "APLD:2027-01-15:25C"):
        with pytest.raises(ValueError):
            opt.parse_options(bad)


def test_parse_leveraged_merges_defaults(monkeypatch):
    m = lev.parse_leveraged("SNXX:SNDK:2, XYZU:XYZ, SQQQ:QQQ:-3")
    assert m["SNXX"].underlying == "SNDK" and m["XYZU"].factor == 2 and m["SQQQ"].factor == -3
    assert "APLX" in m and m["APLX"].label == "2× daily APLD"
    assert m["SQQQ"].label == "3× inverse daily QQQ"
    for bad in ("SNXX", "SNXX:SNDK:x", "SNXX:SNDK:0"):
        with pytest.raises(ValueError):
            lev.parse_leveraged(bad)
    monkeypatch.setenv("OPTIONS", "APLD:2027-01-15:25C:20@6.897")
    monkeypatch.setenv("LEVERAGED_ETFS", "ABCX:ABC:2")
    s = config.load(env_file=None)
    assert s.options[0].contracts == 20 and s.underlying("abcx") == "ABC" and s.underlying("SNXX") == "SNDK"
    assert s.underlying("NVDA") == "NVDA" and s.brief_split


# ------------------------------------------------------------------ leverage math
def test_underlying_needed_straight_line_and_with_swings():
    # 2x fund at half its cost: needs +100%; straight line -> sqrt(2) = +41.4%
    assert lev.underlying_needed(2.0, 2, 0.0, 0.0) == pytest.approx(math.sqrt(2))
    swings = lev.underlying_needed(2.0, 2, 0.87, 0.25)
    assert swings == pytest.approx(math.sqrt(2 * math.exp(0.87 ** 2 * 0.25)))
    assert 1.5 < swings < 1.6  # ~+56%, the SNXX/SanDisk number in the brief
    assert lev.underlying_needed(2.0, -1, 0.0, 0.0) == pytest.approx(0.5)  # inverse: stock must halve
    assert lev.underlying_needed(0, 2, 0.5, 1) is None


def _fund_from(under: pd.Series, factor: float = 2.0, start: float = 20.0) -> pd.Series:
    r = under.pct_change().fillna(0)
    return start * (1 + factor * r).cumprod()


def test_leverage_view_shows_decay_on_a_choppy_flat_path():
    rng = np.random.default_rng(3)
    r = rng.normal(0, 0.04, 120)
    r -= r.mean()  # ends roughly flat, lots of chop
    idx = pd.bdate_range("2026-04-01", periods=121)
    under = pd.Series(100 * np.exp(np.r_[0, np.cumsum(r)]), index=idx)
    fund = _fund_from(under)
    v = lev.view(lev.DEFAULT_LEVERAGED["SNXX"], fund, under, cost=float(fund.iloc[-1]) * 2, window=60)
    assert v.lag > 2  # the fund fell short of 2x the stock
    text = "\n".join(v.lines(float(fund.iloc[-1]) * 2))
    assert "Last 60 sessions: SNDK" in text and "decay cost" in text
    assert "Back to your $" in text and "+100%" in text and "+41% in a straight line" in text
    assert v.with_swings > v.straight


# ------------------------------------------------------------------ options math
def test_black_scholes_parity_theta_and_iv_roundtrip():
    S, K, T, vol = 18.05, 25.0, 91 / 365, 0.9
    c, p = opt.bs(S, K, T, vol, "C"), opt.bs(S, K, T, vol, "P")
    assert c.price - p.price == pytest.approx(S - K * math.exp(-opt.RATE * T), abs=1e-9)
    assert 0 < c.delta < 1 and -1 < p.delta < 0 and c.theta_day < 0
    assert opt.implied_vol(c.price, S, K, T, "C") == pytest.approx(vol, abs=1e-4)
    assert opt.implied_vol(0.0001, S, 5.0, T, "C") is None  # below intrinsic
    assert opt.prob_beyond(S, 26.33, T, vol, "C") == pytest.approx(0.16, abs=0.03)


def test_option_view_matches_robinhood_numbers():
    h = opt.OptionHolding("APLD", date(2027, 1, 15), 25.0, "C", 20, 6.897)
    q = opt.OptionQuote(bid=1.26, ask=1.39, last=1.33, iv=0.8994)
    v = opt.build_view(h, TODAY, 18.05, q, earnings=date(2027, 1, 6))
    assert v.days_left == 91 and v.mark == pytest.approx(1.325)
    assert v.value == pytest.approx(2650) and v.paid == pytest.approx(13794) and v.pnl == pytest.approx(-11144)
    assert v.beat_selling == pytest.approx(26.325) and v.cost_back == pytest.approx(31.897)
    assert v.move(v.beat_selling) == pytest.approx(45.8, abs=0.1)
    assert -40 < v.decay_day < -25  # Robinhood showed -$33/day (theta 0.0164 x 2,000 shares)
    text = "\n".join(v.lines())
    assert "beats selling today above $26.32" in text or "beats selling today above $26.33" in text
    assert "your cost back above $31.90 (+77%)" in text and "91 days left" in text
    assert "earnings Jan 06 lands 9 days before expiry" in text and "time decay -$" in text
    soon = opt.build_view(h, TODAY, 18.05, q, earnings=date(2026, 10, 29))
    assert "earnings Oct 29 (13 days)" in "\n".join(soon.lines()) and "IV crush" in "\n".join(soon.lines())
    far = opt.build_view(opt.OptionHolding("INTC", date(2027, 6, 17), 100, "C", 1, 25), TODAY, 89.8,
                         opt.OptionQuote(14.2, 14.5, 14.35, 0.59), earnings=date(2027, 1, 28))
    assert "📅" not in "\n".join(far.lines())  # a report months away, months before expiry: no flag


def test_option_view_no_bid_wide_spread_and_missing_quote():
    h = opt.OptionHolding("DKNG", date(2027, 3, 19), 37.5, "C", 3, 0.8433)
    v = opt.build_view(h, TODAY, 18.91, opt.OptionQuote(bid=0.0, ask=0.37, last=0.27, iv=None))
    assert v.mark == pytest.approx(0.185) and "no bid right now" in "\n".join(v.lines())
    h2 = opt.OptionHolding("APLD", date(2027, 6, 17), 25.0, "C", 5, 5.23)
    v2 = opt.build_view(h2, TODAY, 18.05, opt.OptionQuote(bid=2.74, ask=3.70, last=3.2, iv=0.866))
    assert "wide spread $2.74 / $3.70" in "\n".join(v2.lines())
    v3 = opt.build_view(h2, TODAY, 18.05, None)
    assert v3.value is None and "no quote" in v3.lines()[0]
    put = opt.build_view(opt.OptionHolding("SPY", date(2026, 12, 18), 700, "P", 1, 10.0), TODAY, 763.3,
                         opt.OptionQuote(4.0, 4.4, 4.2, 0.2))
    assert put.beat_selling == pytest.approx(695.8) and put.cost_back == 690 and "below $" in "\n".join(put.lines())


# ------------------------------------------------------------------ data adapters
class FakeTicker:
    def __init__(self, info=None, q=None, rec=None, options=(), chain=None):
        self.info, self.quarterly_income_stmt, self.recommendations = info or {}, q, rec
        self.options, self._chain = options, chain

    def option_chain(self, exp):
        return self._chain


def test_fetch_fundamentals_prefers_latest_quarter(monkeypatch):
    cols = pd.to_datetime(["2026-07-03", "2026-04-03", "2026-01-02", "2025-10-03", "2025-06-27"])
    q = pd.DataFrame([[8965, 5950, 3025, 2308, 1901], [6903, 3615, 803, 112, -23]],
                     index=["Total Revenue", "Net Income"], columns=cols) * 1e6
    rec = pd.DataFrame([{"period": "0m", "strongBuy": 10, "buy": 17, "hold": 5, "sell": 1, "strongSell": 0}])
    info = {"quoteType": "EQUITY", "trailingPE": 19.03, "forwardPE": 7.2, "revenueGrowth": 2.9, "profitMargins": 0.4,
            "targetMeanPrice": 2275.85, "targetLowPrice": 1400, "targetHighPrice": 3600, "numberOfAnalystOpinions": 33}
    data._FUND_CACHE.clear()
    monkeypatch.setattr(data, "_yf", lambda: types.SimpleNamespace(Ticker=lambda s: FakeTicker(info, q, rec)))
    f = data.fetch_fundamentals("SNDK", TODAY)
    assert f.revenue_growth == pytest.approx((8965 / 1901 - 1) * 100) and f.net_margin == pytest.approx(77, abs=0.1)
    assert (f.buy, f.hold, f.sell) == (27, 5, 1)
    lines = f.lines(1298.75, "SNDK")
    assert lines[0] == "SNDK: revenue +372% y/y · net margin 77% · P/E 19 (fwd 7)"
    assert lines[1] == "Analysts: 27 Buy / 5 Hold / 1 Sell · avg target $2,275.85 (+75%), range $1,400–3,600"
    data._FUND_CACHE.clear()
    monkeypatch.setattr(data, "_yf", lambda: types.SimpleNamespace(Ticker=lambda s: FakeTicker({"quoteType": "ETF"})))
    assert data.fetch_fundamentals("SPY", TODAY) is None


def test_fetch_option_quote(monkeypatch):
    calls = pd.DataFrame({"strike": [20.0, 25.0], "bid": [3.0, 1.26], "ask": [3.2, 1.39],
                          "lastPrice": [3.1, 1.33], "impliedVolatility": [0.85, 0.9]})
    chain = types.SimpleNamespace(calls=calls, puts=calls.iloc[:0])
    fake = FakeTicker(options=("2027-01-15",), chain=chain)
    monkeypatch.setattr(data, "_yf", lambda: types.SimpleNamespace(Ticker=lambda s: fake))
    q = data.fetch_option_quote("APLD", date(2027, 1, 15), 25.0, "C")
    assert (q.bid, q.ask, q.iv) == (1.26, 1.39, 0.9)
    assert data.fetch_option_quote("APLD", date(2027, 2, 19), 25.0, "C") is None  # expiry not listed
    assert data.fetch_option_quote("APLD", date(2027, 1, 15), 25.0, "P") is None


# ------------------------------------------------------------------ end to end
@pytest.fixture
def portfolio_network(monkeypatch, tmp_path):
    idx = uptrend_pullback().index
    sndk = choppy(n=404)
    sndk.index = idx
    fund_close = _fund_from(sndk["Close"], start=20.0)
    snxx = sndk.copy()
    for c in ("Open", "High", "Low", "Close"):
        snxx[c] = fund_close * (sndk[c] / sndk["Close"])
    frames = {**calm_market(idx), "NVDA": uptrend_pullback(), "TSLA": downtrend_rally(), "SNDK": sndk, "SNXX": snxx,
              "APLD": make_ohlc([0.0] * len(idx), start=18.0, seed=9),
              "SOXX": make_ohlc([0.0005] * len(idx), seed=7), "XLK": make_ohlc([0.0008] * len(idx), seed=5)}
    for f in frames.values():
        f.index = idx
    asked = []
    monkeypatch.setattr(data, "fetch_history", lambda syms, period=None, retries=2: {s: frames[s] for s in syms if s in frames})
    monkeypatch.setattr(data, "fetch_fred", lambda sid, timeout=15: pd.Series(3.0, index=idx))

    def earnings(sym, today=None):
        asked.append(sym)
        if sym in ("SNXX",):
            return EarningsInfo("none")  # funds have no earnings – the bug this guards against
        return EarningsInfo("known", idx[-1].date() + timedelta(days=10))
    monkeypatch.setattr(data, "get_next_earnings", earnings)
    monkeypatch.setattr(data, "fetch_news", lambda s, limit=5: [{"title": f"{s} headline", "publisher": "Reuters"}])
    monkeypatch.setattr(data, "fetch_fundamentals", lambda s, today=None: Fundamentals(
        s, revenue_growth=372.0, net_margin=77.0, pe=19.0, buy=27, hold=5, sell=1, target_mean=2275.85))
    monkeypatch.setattr(data, "fetch_option_quote", lambda u, e, k, r: opt.OptionQuote(1.26, 1.39, 1.33, 0.9))
    monkeypatch.setattr(sector.SectorMap, "_lookup", staticmethod(lambda s: ({"NVDA": "SOXX", "SNDK": "SOXX"}.get(s, "XLK"), True)))
    now = datetime.combine(idx[-1].date(), datetime.min.time(), tzinfo=ET).replace(hour=17)
    monkeypatch.setattr(scanner, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: now)}))
    s = config.Settings(data_dir=tmp_path, watchlist=["NVDA"], events_file=tmp_path / "none.yaml",
                        portfolio=[config.Holding("NVDA", 10, 300.0), config.Holding("SNXX", 2400, 18.30),
                                   config.Holding("TSLA", 5, None)],
                        options=[opt.OptionHolding("APLD", idx[-1].date() + timedelta(days=91), 25.0, "C", 20, 6.897)],
                        brief_deep_stocks=2)
    return s, idx, asked


def test_brief_is_two_messages_with_depth(portfolio_network):
    s, idx, asked = portfolio_network
    now = datetime.combine(idx[-1].date(), datetime.min.time(), tzinfo=PT).replace(hour=6)
    news, stocks = brief.build_messages(s, now=now, use_ai=False)
    assert news.startswith("📰 *") and "Market mood: NORMAL (0/5)" in news and "Coming up" in news
    assert "SNDK earnings (your SNXX)" in news
    assert "not financial advice" not in news and "not financial advice" in stocks
    assert stocks.startswith("📊 *Your stocks")
    assert "Stocks/ETFs $" in stocks and "Leveraged ETFs:" in stocks and "Options $2,650 vs $13.8K paid" in stocks
    assert "2× daily SNDK" in stocks and "SNDK: revenue +372% y/y" in stocks and "27 Buy / 5 Hold / 1 Sell" in stocks
    assert "Back to your $18.30" in stocks and "SNDK earnings" in stocks
    assert "*The rest*" in stocks and "• *TSLA*" in stocks  # third holding by value -> one line
    tsla = next(line for line in stocks.splitlines() if line.startswith("• *TSLA*"))
    assert tsla.endswith(("downtrend", "earnings blackout", "no clear trend")) or "· earnings" in tsla
    assert "rules don't support" not in tsla and "PUT entry needs" not in tsla  # one-liners use the short form
    assert "*APLD $25 call" in stocks and "beats selling today above $26.32" in stocks
    assert "SNXX" not in asked and "SNDK" in asked  # leveraged ETF -> the company's earnings date
    assert "SNDK headline" in stocks  # news for the company, not the fund
    one = brief.build(s, now=now, use_ai=False)
    s.brief_split = False
    assert brief.build_messages(s, now=now, use_ai=False) == [one]


def test_scanner_blocks_leveraged_etf_before_company_earnings(portfolio_network):
    s, idx, asked = portfolio_network
    ctx = scanner.build_context(s, ["SNXX"])
    assert ctx.sectors["SNXX"] == "SOXX"  # sector from SanDisk, not the fund
    sig = scanner.analyze("SNXX", ctx, s, force_earnings=True)
    assert sig.earnings.status == "known" and asked[-1] == "SNDK"


def test_tracker_sends_news_then_stocks_and_retries_only_the_missing_part(portfolio_network, monkeypatch):
    s, idx, _ = portfolio_network
    monkeypatch.setattr(brief, "build_messages", lambda st, now=None: ["NEWS", "STOCKS"])
    t = Tracker(s)
    t.brief_gap_seconds = 0
    sent, fail = [], {"STOCKS"}
    t.notifier.send = lambda text, subject, payload=None: (sent.append((subject.split()[0], text))
                                                           or {"whatsapp": text not in fail})
    now = datetime(2026, 10, 17, 6, 0, tzinfo=PT)
    with pytest.raises(RuntimeError):
        t.send_brief(now)
    assert [x[1] for x in sent] == ["NEWS", "STOCKS"] and t.state["last_brief"] is None
    fail.clear()
    sent.clear()
    t.send_brief(now + timedelta(minutes=20))
    assert sent == [("Your", "STOCKS")] and t.state["last_brief"] == "2026-10-17"


# ------------------------------------------------------------------ review follow-ups
def _b(kind, text=None, urls=()):
    return types.SimpleNamespace(type=kind, text=text, citations=[types.SimpleNamespace(url=u) for u in urls])


P1 = "*What's moving markets*\n• Chips fell\n*Lesson of the day*\nSpreads.\n"


@pytest.mark.parametrize("blocks", [
    # A: part 1 + marker, then a search, then part 2
    [_b("text", "Let me search.", ()), _b("server_tool_use"), _b("web_search_tool_result"),
     _b("text", P1 + "===STOCKS===\n", ["https://reuters.com/a"]), _b("server_tool_use"), _b("web_search_tool_result"),
     _b("text", "*SNXX*\n• Why it moved: memory", ["https://cnbc.com/b"])],
    # B: marker only after the search
    [_b("text", P1, ["https://reuters.com/a"]), _b("server_tool_use"), _b("web_search_tool_result"),
     _b("text", "===STOCKS===\n*SNXX*\n• Why it moved: memory", ["https://cnbc.com/b"])],
    # C: marker split across two text blocks
    [_b("text", P1 + "===STO", ["https://reuters.com/a"]), _b("text", "CKS===\n*SNXX*\n• Why it moved: memory",
                                                              ["https://cnbc.com/b"])],
    # no marker at all: split at the first focus-symbol header
    [_b("text", "Here is the brief.\n" + P1, ["https://reuters.com/a"]),
     _b("text", "*SNXX*\n• Why it moved: memory", ["https://cnbc.com/b"])],
])
def test_split_ai_handles_searches_between_parts(blocks):
    news, nsrc, stocks, ssrc = brief.split_ai(blocks, ["SNXX", "SNDK"])
    assert news.startswith("*What's moving markets*") and news.endswith("Spreads.")
    assert "STO" not in news and "Let me search" not in news and "Here is the brief" not in news
    assert stocks.startswith("*SNXX*") and nsrc == ["reuters.com"] and ssrc == ["cnbc.com"]


def test_totals_only_compare_holdings_that_have_a_cost():
    hv = lambda sym, sh, cost, px, prev: brief.HoldingView(  # noqa: E731
        config.Holding(sym, sh, cost), types.SimpleNamespace(price=px), prev_close=prev, last=px)
    b = types.SimpleNamespace(holdings=[hv("NVDA", 10, 300.0, 350.0, 340.0), hv("TSLA", 5, None, 400.0, 400.0)],
                              options=[])
    line = brief._totals(b)[0]
    assert "Stocks/ETFs $5,500" in line and "1 with a cost: $3,500 vs $3,000 (+17%)" in line
    assert "last session +$100 (+1.9%)" in line
    o1 = opt.build_view(opt.OptionHolding("APLD", date(2027, 1, 15), 25, "C", 1, 5.0), TODAY, 18, opt.OptionQuote(2.0, 2.2, 2.1, 0.9))
    o2 = opt.build_view(opt.OptionHolding("INTC", date(2027, 6, 17), 100, "C", 1), TODAY, 90, opt.OptionQuote(14.1, 14.3, 14.2, 0.6))
    b.options, b.holdings = [o1, o2], []
    assert "vs $500 paid (-$290 on the 1 with a cost)" in brief._totals(b)[0]


def test_option_marks_on_odd_quotes_and_positive_theta():
    assert opt.OptionQuote(1.30, 1.25, 1.0, None).mark == pytest.approx(1.275)  # crossed
    assert opt.OptionQuote(1.30, None, 1.0, None).mark == 1.30  # bid only
    closed = opt.OptionQuote(0.0, 0.0, 2.10, None)
    assert closed.mark == 2.10 and not closed.live and not closed.no_bid
    v = opt.build_view(opt.OptionHolding("APLD", date(2027, 1, 15), 25, "C", 1, 5.0), TODAY, 18.05, closed)
    text = "\n".join(v.lines())
    assert "no live quote – priced at the last trade $2.10" in text and "no bid right now" not in text
    deep_put = opt.build_view(opt.OptionHolding("XYZ", date(2027, 10, 16), 100, "P", 10, 40.0), TODAY, 50.0,
                              opt.OptionQuote(48.0, 49.0, 48.5, 0.3))
    assert deep_put.decay_day > 0 and "time value +$" in "\n".join(deep_put.lines())
    expired = opt.build_view(opt.OptionHolding("XYZ", date(2026, 10, 9), 100, "P", 1, 4.0), TODAY, 50.0, None)
    assert expired.lines() == ["*XYZ $100 put Oct 09 '26* ×1 – expired; remove it from OPTIONS"]


def test_revenue_growth_matches_the_year_ago_quarter_by_date(monkeypatch):
    cols = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30", "2025-03-31"])  # Sep-25 missing
    q = pd.DataFrame([[150, 140, 130, 100, 90]], index=["Total Revenue"], columns=cols)
    data._FUND_CACHE.clear()
    monkeypatch.setattr(data, "_yf", lambda: types.SimpleNamespace(Ticker=lambda s: FakeTicker({"quoteType": "EQUITY"}, q)))
    assert data.fetch_fundamentals("ABC", TODAY).revenue_growth == pytest.approx(50.0)  # vs 2025-06-30, not 2025-03-31


def test_sector_override_and_inverse_funds(portfolio_network):
    s, idx, _ = portfolio_network
    s.sector_overrides = {"SNXX": "XLK"}
    s.leveraged = {**s.leveraged, "SNDQ": lev.LeveragedETF("SNDQ", "SNDK", -1)}
    ctx = scanner.build_context(s, ["SNXX"])
    assert ctx.sectors["SNXX"] == "XLK"  # an explicit override beats the underlying's sector
    ctx.sectors["SNDQ"] = "SOXX"
    ctx.history["SNDQ"] = ctx.history["SNXX"]
    ctx.sector_states["SOXX"] = sector.SectorState("SOXX", False, True, 30.0, -8.0, "breaking")
    sig = scanner.analyze("SNDQ", ctx, s)
    assert sig.sector is None and sig.status != "SECTOR_BLOCK"  # inverse fund: the CALL guard does not apply


def test_tracker_stops_at_first_failure_and_resets_when_message_count_changes(portfolio_network, monkeypatch):
    s, idx, _ = portfolio_network
    parts = ["NEWS", "STOCKS"]
    monkeypatch.setattr(brief, "build_messages", lambda st, now=None: list(parts))
    t = Tracker(s)
    t.brief_gap_seconds = 0
    sent, fail = [], {"NEWS"}
    t.notifier.send = lambda text, subject, payload=None: sent.append(text) or {"whatsapp": text not in fail}
    now = datetime(2026, 10, 17, 6, 0, tzinfo=PT)
    with pytest.raises(RuntimeError):
        t.send_brief(now)
    assert sent == ["NEWS"]  # stocks held back so it can't arrive before the news
    fail.clear()
    t.state["brief_parts"] = {"day": "2026-10-17", "count": 2, "sent": [0]}
    parts[:] = ["NEWS+STOCKS"]  # BRIEF_SPLIT flipped to false after a restart
    sent.clear()
    t.send_brief(now + timedelta(minutes=20))
    assert sent == ["NEWS+STOCKS"] and t.state["last_brief"] == "2026-10-17"


def test_dry_run_brief_does_not_touch_state(portfolio_network, monkeypatch):
    s, idx, _ = portfolio_network
    monkeypatch.setattr(brief, "build_messages", lambda st, now=None: ["NEWS", "STOCKS"])
    t = Tracker(s, dry_run=True)
    t.send_brief(datetime(2026, 10, 17, 6, 0, tzinfo=PT))
    assert t.state["last_brief"] is None and "brief_parts" not in t.state
