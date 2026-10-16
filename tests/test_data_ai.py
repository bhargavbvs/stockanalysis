"""Data-shape and AI-section tests with fake yfinance / requests / anthropic objects."""

import sys
import types
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from conftest import make_ohlc
from stockbot import brief, config, data
from stockbot.data import EarningsInfo

TODAY = date(2026, 10, 16)


# ------------------------------------------------------------------ fetch_history
def _multi(frames: dict) -> pd.DataFrame:
    return pd.concat(frames, axis=1)  # (Ticker, Price) MultiIndex like group_by="ticker"


def test_fetch_history_multiindex_and_missing(monkeypatch):
    a, b = make_ohlc([0.001] * 30), make_ohlc([0.002] * 30, seed=2)
    a.index = a.index.tz_localize("America/New_York")
    b.index = b.index.tz_localize("America/New_York")
    b.loc[b.index[-1], "Close"] = float("nan")  # half-empty last row
    raw = _multi({"AAA": a, "BBB": b})
    calls = []
    fake = types.SimpleNamespace(download=lambda syms, **kw: calls.append(list(syms)) or raw)
    monkeypatch.setattr(data, "_yf", lambda: fake)
    monkeypatch.setattr(data.time, "sleep", lambda *_: None)
    out = data.fetch_history(["aaa", "BBB", "ZZZ"], retries=1)
    assert set(out) == {"AAA", "BBB"}
    assert out["AAA"].index.tz is None and len(out["BBB"]) == 29
    assert calls == [["AAA", "BBB", "ZZZ"], ["ZZZ"]]  # retried only the missing symbol


def test_fetch_history_download_error(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("no network")
    monkeypatch.setattr(data, "_yf", lambda: types.SimpleNamespace(download=boom))
    monkeypatch.setattr(data.time, "sleep", lambda *_: None)
    assert data.fetch_history(["AAA"], retries=1) == {}


# ------------------------------------------------------------------ earnings (fail closed)
class FakeTicker:
    def __init__(self, calendar=None, dates=None, info=None, raise_info=False):
        self._cal, self._dates, self._info, self._raise = calendar, dates, info, raise_info

    @property
    def calendar(self):
        return self._cal

    def get_earnings_dates(self, limit=12):
        if isinstance(self._dates, Exception):
            raise self._dates
        return self._dates

    @property
    def info(self):
        if self._raise:
            raise RuntimeError("blocked")
        return self._info or {}


def _with(monkeypatch, ticker):
    data._EARNINGS_CACHE.clear()
    monkeypatch.setattr(data, "_yf", lambda: types.SimpleNamespace(Ticker=lambda s: ticker))


def test_earnings_known_from_calendar(monkeypatch):
    _with(monkeypatch, FakeTicker(calendar={"Earnings Date": [date(2026, 10, 28), date(2026, 10, 29)]}))
    e = data.get_next_earnings("MSFT", TODAY)
    assert e == EarningsInfo("known", date(2026, 10, 28)) and e.within(TODAY, 14)


def test_earnings_empty_results_are_unknown_not_none(monkeypatch):
    """yfinance swallows HTTP errors and returns {} / None – that is NOT 'no earnings'."""
    _with(monkeypatch, FakeTicker(calendar={}, dates=None, info={}))
    e = data.get_next_earnings("NVDA", TODAY)
    assert e.status == "unknown" and e.within(TODAY, 14) is None
    assert ("NVDA", TODAY) not in data._EARNINGS_CACHE  # retried next time


def test_earnings_none_needs_evidence(monkeypatch):
    idx = pd.DatetimeIndex([pd.Timestamp("2026-07-29", tz="America/New_York")])
    _with(monkeypatch, FakeTicker(calendar={}, dates=pd.DataFrame({"EPS": [1.0]}, index=idx)))
    assert data.get_next_earnings("X", TODAY).status == "none"
    _with(monkeypatch, FakeTicker(calendar={}, dates=None, info={"quoteType": "ETF"}))
    assert data.get_next_earnings("SPY", TODAY).status == "none"
    _with(monkeypatch, FakeTicker(calendar={}, dates=ValueError("x"), raise_info=True))
    assert data.get_next_earnings("Y", TODAY).status == "unknown"


def test_earnings_from_earnings_dates_table(monkeypatch):
    idx = pd.DatetimeIndex([pd.Timestamp("2027-01-28 16:00", tz="America/New_York"),
                            pd.Timestamp("2026-07-29 16:00", tz="America/New_York")])
    _with(monkeypatch, FakeTicker(calendar=None, dates=pd.DataFrame({"EPS": [None, 1.0]}, index=idx)))
    assert data.get_next_earnings("Z", TODAY) == EarningsInfo("known", date(2027, 1, 28))


# ------------------------------------------------------------------ FRED
class Resp:
    def __init__(self, text, code=200):
        self.text, self.status_code = text, code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.mark.parametrize("text,ok", [
    ("observation_date,BAMLH0A0HYM2\n2026-10-13,3.20\n2026-10-14,.\n2026-10-15,3.25\n", True),
    ("DATE,BAMLH0A0HYM2\n2026-10-13,3.20\n", True),
    ("<html><body>FRED is down for maintenance</body></html>", False),
    ("", False),
])
def test_fetch_fred_parses_or_returns_none(monkeypatch, text, ok):
    import requests

    monkeypatch.setattr(requests, "get", lambda url, timeout=15: Resp(text))
    s = data.fetch_fred("BAMLH0A0HYM2")
    if ok:
        assert s is not None and s.iloc[-1] > 3 and s.index.is_monotonic_increasing
    else:
        assert s is None


# ------------------------------------------------------------------ AI section parsing
def _blk(kind, **kw):
    return types.SimpleNamespace(type=kind, **kw)


def _cite(url):
    return types.SimpleNamespace(url=url, title="t")


class FakeMessages:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def create(self, **kw):
        self.calls.append(kw)
        return self.responses.pop(0)


def _install_fake_anthropic(monkeypatch, responses):
    msgs = FakeMessages(responses)
    mod = types.SimpleNamespace(Anthropic=lambda **kw: types.SimpleNamespace(messages=msgs))
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    return msgs


def _brief_data():
    from stockbot import regime as rg, scanner
    ctx = scanner.Context(today=TODAY, regime=rg.Regime(asof=TODAY, score=1, components=[]))
    return brief.BriefData(datetime(2026, 10, 16, 6, tzinfo=ZoneInfo("America/Los_Angeles")), ctx, [], [], [], [])


def test_ai_take_accumulates_pause_turn_and_keeps_sources(monkeypatch):
    first = types.SimpleNamespace(stop_reason="pause_turn", content=[
        _blk("text", text="Let me search."), _blk("server_tool_use", input={"query": "stocks today"}),
        _blk("web_search_tool_result", content=[])])
    second = types.SimpleNamespace(stop_reason="end_turn", content=[
        _blk("text", text="*What's moving markets*\n• Chips fell", citations=[_cite("https://www.reuters.com/x")]),
        _blk("text", text="\n*Lesson of the day*\nSpreads matter.", citations=[_cite("https://cnbc.com/y")])])
    msgs = _install_fake_anthropic(monkeypatch, [first, second])
    s = config.Settings(anthropic_api_key="k")
    text = brief.ai_take(_brief_data(), s)
    assert text.startswith("*What's moving markets*") and "Let me search" not in text
    assert "_Sources: reuters.com, cnbc.com_" in text
    # the continuation resent the paused assistant blocks unchanged
    cont = msgs.calls[1]["messages"]
    assert cont[1]["role"] == "assistant" and cont[1]["content"] == first.content
    assert msgs.calls[0]["tools"][0]["type"] == "web_search_20250305"


def test_ai_take_failure_returns_none(monkeypatch):
    class Boom:
        def create(self, **kw):
            raise TimeoutError("slow")
    monkeypatch.setitem(sys.modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda **kw: types.SimpleNamespace(messages=Boom())))
    assert brief.ai_take(_brief_data(), config.Settings(anthropic_api_key="k")) is None
    assert brief.ai_take(_brief_data(), config.Settings()) is None  # no key -> skipped


# ------------------------------------------------------------------ alerts: redaction & encoding
def test_secrets_never_logged(monkeypatch, caplog):
    import requests

    from stockbot.alerts import Notifier
    s = config.Settings(telegram_token="12345:SECRETTOKEN", telegram_chat_id="1",
                        whatsapp_phone="+15105550000", callmebot_api_key="SECRETKEY")

    class Sess:
        def get(self, url, **kw):
            raise requests.ConnectionError(f"GET {url}?apikey=SECRETKEY&phone=%2B15105550000 failed")

        def post(self, url, **kw):
            return types.SimpleNamespace(status_code=401, text="bad token 12345:SECRETTOKEN", json=lambda: {})

    with caplog.at_level("INFO"):
        res = Notifier(s, session=Sess()).send("hi")
    assert res == {"whatsapp": False, "telegram": False}
    assert "SECRET" not in caplog.text and "5105550000" not in caplog.text


def test_callmebot_chunks_fit_url_limits(monkeypatch):
    import urllib.parse

    from stockbot.alerts import Notifier
    monkeypatch.setattr("stockbot.alerts.time.sleep", lambda *_: None)
    sent = []
    sess = types.SimpleNamespace(get=lambda url, params=None, timeout=None: sent.append(params["text"])
                                 or types.SimpleNamespace(status_code=200, text="queued"))
    telugu = "\n".join("📈 మార్కెట్ మూడ్ జాగ్రత్తగా ఉంది – " * 3 for _ in range(60))
    n = Notifier(config.Settings(whatsapp_phone="+1", callmebot_api_key="k"), session=sess)
    assert n.send_whatsapp(telugu)
    assert len(sent) > 1 and all(len(urllib.parse.quote(t, safe="")) <= 3000 for t in sent)


def test_telegram_falls_back_to_plain_text_on_400():
    from stockbot.alerts import Notifier
    posts = []

    def post(url, data=None, timeout=None):
        posts.append(data)
        code = 400 if "parse_mode" in data else 200
        return types.SimpleNamespace(status_code=code, text="can't parse entities", json=lambda: {})

    n = Notifier(config.Settings(telegram_token="t:1", telegram_chat_id="1"), session=types.SimpleNamespace(post=post))
    assert n.send_telegram("*a _b* c_")
    assert "parse_mode" in posts[0] and "parse_mode" not in posts[1]


# ------------------------------------------------------------------ bot access control
def test_bot_denies_by_default():
    pytest.importorskip("telegram")
    from stockbot.bot import build_app, is_allowed
    assert not is_allowed(config.Settings(), 42)
    assert is_allowed(config.Settings(allowed_chat_ids={"42"}), 42)
    assert build_app(config.Settings(telegram_token="123:abc")) is not None


def test_tzdata_and_requirements_pins():
    from pathlib import Path

    reqs = Path("requirements.txt").read_text()
    assert "tzdata" in reqs and "yfinance>=" in reqs and "<" in reqs
