from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from conftest import calm_market, choppy, downtrend_rally, make_ohlc, uptrend_pullback
from stockbot import brief, config, data, regime as rg, scanner, sector
from stockbot.alerts import Notifier
from stockbot.data import EarningsInfo
from stockbot.report import signal_message, split_message, to_discord, to_plain, to_telegram_html
from stockbot.signals import SIGNAL, evaluate
from stockbot.tracker import Tracker, in_scan_window

ET = ZoneInfo("America/New_York")
PT = ZoneInfo("America/Los_Angeles")


# ----------------------------------------------------------------- report
def test_telegram_html_escapes_and_bolds():
    out = to_telegram_html("*NVDA* < $200 & _rising_ – a*b")
    assert out == "<b>NVDA</b> &lt; $200 &amp; <i>rising</i> – a*b"


def test_other_formats():
    assert to_discord("*Hi* there") == "**Hi** there"
    assert to_plain("*Hi* _there_") == "Hi there"


def test_split_message_respects_limit():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(200))
    chunks = split_message(text, 500)
    assert all(len(c) <= 500 for c in chunks)
    assert "".join(c.replace("\n", "") for c in chunks) == text.replace("\n", "")


def test_signal_message_has_plan():
    df = uptrend_pullback()
    s = evaluate("NVDA", df, earnings=EarningsInfo("none"), today=df.index[-1].date(), account_size=10_000)
    msg = signal_message(s)
    assert "*NVDA – BUY CALL SIGNAL" in msg and "Stop $" in msg and "Target 2R" in msg and "shares" in msg
    assert "not financial advice" in msg


# ----------------------------------------------------------------- alerts
class FakeResp:
    def __init__(self, code=200, text="Message queued"):
        self.status_code, self.text = code, text

    def json(self):
        return {}


class FakeSession:
    def __init__(self, resp=None):
        self.calls, self.resp = [], resp or FakeResp()

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self.resp

    def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self.resp


def _settings(**kw):
    s = config.Settings()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_callmebot_whatsapp(monkeypatch):
    monkeypatch.setattr("stockbot.alerts.time.sleep", lambda *_: None)
    sess = FakeSession()
    n = Notifier(_settings(whatsapp_phone="+15105550000", callmebot_api_key="k"), session=sess)
    assert n.channels == ["whatsapp"]
    res = n.send("hello\n" * 400)  # long -> several chunks
    assert res == {"whatsapp": True}
    assert len(sess.calls) > 1
    method, url, kw = sess.calls[0]
    assert method == "GET" and "callmebot" in url and kw["params"]["phone"] == "+15105550000"


def test_callmebot_error_is_reported(monkeypatch):
    sess = FakeSession(FakeResp(200, "<b>ERROR</b>: invalid apikey"))
    n = Notifier(_settings(whatsapp_phone="+1", callmebot_api_key="bad"), session=sess)
    assert n.send("hi") == {"whatsapp": False}


def test_twilio_and_telegram():
    sess = FakeSession(FakeResp(201, "{}"))
    s = _settings(whatsapp_provider="twilio", whatsapp_phone="+15105550000", twilio_account_sid="AC1",
                  twilio_auth_token="t", telegram_token="T", telegram_chat_id="42")
    n = Notifier(s, session=sess)
    assert n.channels == ["whatsapp", "telegram"]
    n.send_whatsapp("*hi*")
    assert sess.calls[0][2]["data"]["To"] == "whatsapp:+15105550000"
    sess.resp = FakeResp(200, "{}")
    assert n.send_telegram("*bold* <x>")
    assert sess.calls[-1][2]["data"]["text"] == "<b>bold</b> &lt;x&gt;"
    assert sess.calls[-1][2]["data"]["parse_mode"] == "HTML"


def test_no_channels_does_not_crash():
    assert Notifier(_settings()).send("hi") == {}


# ----------------------------------------------------------------- config
def test_parse_portfolio():
    p = config.parse_portfolio(" nvda:10@120.5, AAPL:5 ,msft ")
    assert p == [config.Holding("NVDA", 10, 120.5), config.Holding("AAPL", 5, None), config.Holding("MSFT")]


def test_load_from_env(monkeypatch):
    monkeypatch.setenv("WATCHLIST", "aapl, nvda")
    monkeypatch.setenv("PORTFOLIO", "NVDA:2@100,TSLA")
    monkeypatch.setenv("MIN_CONFIDENCE", "high")
    monkeypatch.setenv("BRIEF_DAYS", "Mon,Tue")
    s = config.load(env_file=None)
    assert s.scan_symbols == ["AAPL", "NVDA", "TSLA"]
    assert s.min_confidence == "HIGH" and s.brief_days == ("mon", "tue")


# ----------------------------------------------------------------- tracker
def test_scan_window():
    assert in_scan_window(datetime(2026, 10, 16, 10, 0, tzinfo=ET))
    assert in_scan_window(datetime(2026, 10, 16, 16, 10, tzinfo=ET))
    assert not in_scan_window(datetime(2026, 10, 16, 9, 0, tzinfo=ET))
    assert not in_scan_window(datetime(2026, 10, 17, 11, 0, tzinfo=ET))  # Saturday


def test_brief_due_and_retries(tmp_path):
    t = Tracker(_settings(data_dir=tmp_path), dry_run=True)
    assert not t.brief_due(datetime(2026, 10, 16, 5, 59, tzinfo=PT))
    six = datetime(2026, 10, 16, 6, 0, tzinfo=PT)
    assert t.brief_due(six)
    t._brief_attempts["2026-10-16"] = [six]
    assert not t.brief_due(six + timedelta(minutes=5))  # wait before retrying a failure
    assert t.brief_due(six + timedelta(minutes=21))
    t.state["last_brief"] = "2026-10-16"
    assert not t.brief_due(six + timedelta(hours=3))
    t.s.brief_days = ("mon",)
    assert not t.brief_due(datetime(2026, 10, 17, 6, 0, tzinfo=PT))


def test_should_alert_cooldown_and_caution(tmp_path):
    df = uptrend_pullback()
    sig = evaluate("NVDA", df, earnings=EarningsInfo("none"), today=df.index[-1].date())
    t = Tracker(_settings(data_dir=tmp_path, min_confidence="MODERATE"), dry_run=True)
    now = datetime(2026, 10, 16, 10, 0, tzinfo=ET)
    assert t.should_alert(sig, now)
    t.state["alerts"]["NVDA:CALL:SIGNAL"] = (now - timedelta(hours=2)).isoformat()
    assert not t.should_alert(sig, now)
    assert t.should_alert(sig, now + timedelta(hours=23))

    caution = rg.Regime(asof=None, score=2, components=[])
    sig.regime, sig.confidence = caution, "MODERATE"
    t.state["alerts"].clear()
    assert not t.should_alert(sig, now)  # CAUTION needs HIGH for calls
    sig.confidence = "HIGH"
    assert t.should_alert(sig, now)


# ----------------------------------------------------------------- end to end with fake data
@pytest.fixture
def fake_network(monkeypatch, tmp_path):
    idx = uptrend_pullback().index
    frames = {**calm_market(idx), "NVDA": uptrend_pullback(), "TSLA": downtrend_rally(), "AAPL": choppy(n=404),
              "SOXX": make_ohlc([0.0005] * len(idx), seed=7), "XLK": make_ohlc([0.0008] * len(idx), seed=5),
              "ES=F": make_ohlc([0.0005] * len(idx), seed=6), "NQ=F": make_ohlc([0.0005] * len(idx), seed=8)}
    for f in frames.values():
        f.index = idx

    monkeypatch.setattr(data, "fetch_history", lambda syms, period=None, retries=2: {s: frames[s] for s in syms if s in frames})
    monkeypatch.setattr(data, "fetch_fred", lambda sid, timeout=15: pd.Series(3.0, index=idx))
    monkeypatch.setattr(data, "get_next_earnings", lambda s, today=None: EarningsInfo("known", idx[-1].date() + timedelta(days=40)))
    monkeypatch.setattr(data, "fetch_news", lambda s, limit=5: [{"title": f"{s} headline", "publisher": "Reuters"}])
    monkeypatch.setattr(sector.SectorMap, "_lookup", staticmethod(lambda s: ({"NVDA": "SOXX"}.get(s, "XLK"), True)))
    now = datetime.combine(idx[-1].date(), datetime.min.time(), tzinfo=ET).replace(hour=12)
    monkeypatch.setattr(scanner, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: now)}))
    s = _settings(data_dir=tmp_path, watchlist=["NVDA", "AAPL", "TSLA"],
                  portfolio=[config.Holding("NVDA", 10, 300.0), config.Holding("TSLA", 5, None)],
                  events_file=tmp_path / "none.yaml")
    return s, idx


def test_scan_end_to_end(fake_network):
    s, idx = fake_network
    sent = []
    t = Tracker(s, dry_run=False)
    t.notifier.send = lambda text, subject, payload=None: sent.append(subject) or {}
    sigs = {x.symbol: x for x in t.scan(now=datetime.now(ET))}
    assert sigs["NVDA"].status == SIGNAL and sigs["NVDA"].direction == "CALL"
    assert sigs["TSLA"].direction == "PUT"
    assert any("NVDA CALL SIGNAL" in subj for subj in sent)
    assert (s.data_dir / "state.json").exists()


def test_brief_renders_without_ai(fake_network):
    s, idx = fake_network
    text = brief.build(s, now=datetime.combine(idx[-1].date(), datetime.min.time(), tzinfo=PT).replace(hour=6), use_ai=False)
    assert "Market mood: NORMAL (0/5)" in text
    assert "*NVDA*" in text and "vs cost" in text and "valid CALL entry" in text
    assert "*TSLA*" in text and "Headlines" in text
    assert "not financial advice" in text
    assert len(text) < 4000
