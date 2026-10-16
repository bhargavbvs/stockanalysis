"""Long-running service: signal scans + the daily morning brief.

Fixes over the old stock_tracker.py:
  * The brief/earnings job used server-local time ("08:00" on a UTC Railway
    box = 4am ET). Times here carry explicit time zones and NYSE holidays.
  * Any exception used to end the process with exit code 0, so Railway's
    ON_FAILURE restart never kicked in. Job errors are caught and reported;
    a crash of the loop itself exits with code 1.
  * Alert history lived in a committed alert_history.json. State now lives in
    DATA_DIR (mount a Railway volume there so it survives redeploys).

Scan timing
  CONFIRM_ON_CLOSE=true (default): one scan per trading day, 10 minutes after
  the close, on completed daily bars – exactly what the backtest tests.
  CONFIRM_ON_CLOSE=false: also scans every SCAN_INTERVAL_MINUTES during the
  session on the unfinished bar (earlier, but signals can vanish by the close).

Alerts fire when a symbol *becomes* a signal (its previous scan wasn't one in
that direction), and not more than once per ALERT_COOLDOWN_HOURS. State is only
recorded when at least one channel actually delivered the message.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from . import brief as brief_mod, config, marketcal, scanner
from .alerts import Notifier
from .regime import CAUTION
from .report import signal_message, to_plain
from .signals import CONFIDENCE, SETUP, SIGNAL, Signal

log = logging.getLogger("stockbot")
ET = ZoneInfo("America/New_York")
SESSION_OPEN = (9, 30)
AFTER_CLOSE_MIN = 10
BRIEF_CATCHUP = timedelta(hours=3)


def _at(now: datetime, hm: tuple[int, int], plus_min: int = 0) -> datetime:
    return now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0) + timedelta(minutes=plus_min)


def in_scan_window(now: datetime) -> bool:
    """Trading session (holiday-aware) plus 15 minutes after the close."""
    now = now.astimezone(ET)
    if not marketcal.is_trading_day(now.date()):
        return False
    close = marketcal.close_time(now.date())
    return _at(now, SESSION_OPEN) <= now <= _at(now, close, 15)


def after_close_time(now: datetime) -> datetime:
    now = now.astimezone(ET)
    return _at(now, marketcal.close_time(now.date()), AFTER_CLOSE_MIN)


class Tracker:
    def __init__(self, settings: config.Settings, notifier: Optional[Notifier] = None, dry_run: bool = False):
        self.s = settings
        self.notifier = notifier or Notifier(settings)
        self.dry_run = dry_run
        self.state_file = Path(settings.data_dir) / "state.json"
        self.fresh_state = not self.state_file.exists()
        self.state = self._load_state()
        self._last_error_notice: Optional[datetime] = None
        self._brief_attempts: dict[str, list[datetime]] = {}

    # ----------------------------------------------------------------- state
    def _load_state(self) -> dict:
        try:
            st = json.loads(self.state_file.read_text())
        except Exception:
            st = {}
        st.setdefault("alerts", {})
        st.setdefault("last_status", {})
        st.setdefault("last_brief", None)
        st.setdefault("last_close_scan", None)
        return st

    def _save_state(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, indent=1, sort_keys=True))
        except Exception as exc:
            log.warning("could not save state: %s", exc)

    # ---------------------------------------------------------------- output
    def deliver(self, text: str, subject: str, payload: Optional[dict] = None) -> bool:
        """True if at least one channel delivered the message (always True in dry-run)."""
        if self.dry_run:
            print(to_plain(text), "\n" + "-" * 60)
            return True
        results = self.notifier.send(text, subject, payload)
        log.info("sent '%s' -> %s", subject, results or "no channels configured")
        return any(results.values())

    # ----------------------------------------------------------------- scans
    def should_alert(self, sig: Signal, now: datetime) -> bool:
        if sig.status != SIGNAL and not (self.s.alert_setups and sig.status == SETUP):
            return False
        need = self.s.min_confidence_rank
        regime = sig.regime
        if (self.s.strategy.use_regime and sig.direction == "CALL" and regime is not None
                and regime.available and regime.mode == CAUTION):
            need = max(need, CONFIDENCE.index("HIGH"))
        if sig.status == SIGNAL and CONFIDENCE.index(sig.confidence) < need:
            return False
        tag = f"{sig.direction}:{sig.status}"
        if self.state["last_status"].get(sig.symbol) == tag:
            return False  # still the same setup as last scan – already told you
        last = self.state["alerts"].get(f"{sig.symbol}:{tag}")
        if last and now - datetime.fromisoformat(last) < timedelta(hours=self.s.alert_cooldown_hours):
            return False
        return True

    def scan(self, now: Optional[datetime] = None, symbols: Optional[list[str]] = None) -> list[Signal]:
        now = now or datetime.now(ET)
        symbols = symbols or self.s.scan_symbols
        log.info("scanning %d symbols", len(symbols))
        ctx, sigs = scanner.analyze_many(symbols, self.s)
        sent = 0
        for sig in sigs:
            log.info("%-6s %-16s %s", sig.symbol, sig.status, sig.headline)
            tag = f"{sig.direction}:{sig.status}"
            if self.should_alert(sig, now):
                ok = self.deliver(signal_message(sig), f"{sig.symbol} {sig.direction} {sig.status}",
                                  {"symbol": sig.symbol, "status": sig.status, "direction": sig.direction,
                                   "confidence": sig.confidence, "price": sig.price})
                if not ok:
                    continue  # leave state alone so the next scan tries again
                self.state["alerts"][f"{sig.symbol}:{tag}"] = now.isoformat()
                sent += 1
            self.state["last_status"][sig.symbol] = tag
        self._save_state()
        log.info("scan done: %d alerts (%s)", sent, ctx.regime.describe())
        return sigs

    def close_scan_due(self, now: datetime) -> bool:
        now = now.astimezone(ET)
        if not marketcal.is_trading_day(now.date()) or now < after_close_time(now):
            return False
        if now > after_close_time(now) + timedelta(hours=4):
            return False
        return self.state.get("last_close_scan") != now.date().isoformat()

    # ----------------------------------------------------------------- brief
    def _brief_slot(self, now: datetime) -> Optional[datetime]:
        local = now.astimezone(ZoneInfo(self.s.brief_tz))
        if local.strftime("%a").lower()[:3] not in self.s.brief_days:
            return None
        hh, mm = (int(x) for x in self.s.brief_time.split(":"))
        return local.replace(hour=hh, minute=mm, second=0, microsecond=0)

    def brief_due(self, now: datetime) -> bool:
        if not self.s.brief_enabled:
            return False
        slot = self._brief_slot(now)
        if slot is None or not (slot <= now <= slot + BRIEF_CATCHUP):
            return False  # don't send a "morning" brief at 10pm after a restart
        day = slot.date().isoformat()
        if self.state.get("last_brief") == day:
            return False
        tries = self._brief_attempts.get(day, [])
        # failed attempts: retry every 20 minutes, at most 3 times a day
        return len(tries) < 3 and (not tries or now - tries[-1] >= timedelta(minutes=20))

    def send_brief(self, now: Optional[datetime] = None) -> str:
        now = now or datetime.now(ZoneInfo(self.s.brief_tz))
        text = brief_mod.build(self.s, now)
        if not self.deliver(text, f"Morning brief {now:%b %d}"):
            raise RuntimeError("no channel delivered the brief")
        self.state["last_brief"] = now.astimezone(ZoneInfo(self.s.brief_tz)).date().isoformat()
        self._save_state()
        return text

    # ------------------------------------------------------------------ loop
    def _job(self, name: str, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as exc:
            log.exception("%s failed: %s", name, type(exc).__name__)
            now = datetime.now(ET)
            if not self._last_error_notice or now - self._last_error_notice > timedelta(hours=6):
                self._last_error_notice = now
                self.deliver(f"⚠️ *Stock bot:* {name} failed ({type(exc).__name__}). Check the logs.",
                             "Stock bot error")

    def run_forever(self) -> None:
        interval = timedelta(minutes=self.s.scan_interval_minutes)
        mode = ("after the close (completed bars)" if self.s.confirm_on_close
                else f"every {self.s.scan_interval_minutes} min in market hours + after the close")
        log.info("tracker started: %d symbols, scans %s, brief %s %s",
                 len(self.s.scan_symbols), mode, self.s.brief_time, self.s.brief_tz)
        if self.fresh_state:
            log.warning("no saved state in %s – if this shows on every deploy, mount a volume there "
                        "or alerts may repeat after restarts", self.s.data_dir)
        if marketcal.covered_until() < datetime.now(ET).date() + timedelta(days=60):
            log.warning("NYSE holiday list ends %s – extend stockbot/marketcal.py", marketcal.covered_until())

        last_intraday: Optional[datetime] = None
        while True:
            now = datetime.now(ET)
            if self.brief_due(now):
                day = self._brief_slot(now).date().isoformat()
                self._brief_attempts.setdefault(day, []).append(now)
                self._job("morning brief", self.send_brief)
            if self.close_scan_due(now):
                self.state["last_close_scan"] = now.date().isoformat()
                self._job("closing scan", self.scan, now)
            elif (not self.s.confirm_on_close and in_scan_window(now) and now < after_close_time(now)
                  and (last_intraday is None or now - last_intraday >= interval)):
                last_intraday = now
                self._job("scan", self.scan, now)
            time.sleep(30)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Stock signal tracker + morning brief")
    ap.add_argument("--once", action="store_true", help="run one scan now (ignores market hours) and exit")
    ap.add_argument("--brief", action="store_true", help="build and send the morning brief now and exit")
    ap.add_argument("--no-ai", action="store_true", help="brief without the AI section")
    ap.add_argument("--test", action="store_true", help="send a test message to every configured channel")
    ap.add_argument("--symbols", nargs="*", help="override the symbols for --once")
    ap.add_argument("--dry-run", action="store_true", help="print messages instead of sending them")
    ap.add_argument("--env", default=".env", help="env file to load (default .env)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore", "urllib3", "yfinance", "peewee"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # httpx logs URLs that contain bot tokens

    try:
        settings = config.load(args.env)
    except ValueError as exc:
        log.error("configuration error: %s", exc)
        return 2  # a config error won't fix itself by restarting
    tracker = Tracker(settings, dry_run=args.dry_run)

    if args.test:
        ok = tracker.deliver("✅ *Test message* from your stock bot. If you can read this, delivery works.", "Test")
        return 0 if ok else 1
    if args.brief:
        if args.no_ai:
            settings.anthropic_api_key = ""
        tracker.send_brief()
        return 0
    if args.once:
        tracker.scan(symbols=[s.upper() for s in args.symbols] if args.symbols else None)
        return 0
    try:
        tracker.run_forever()
    except KeyboardInterrupt:
        log.info("stopped by user")
        return 0
    except Exception as exc:  # loop itself crashed – exit non-zero so Railway restarts us
        log.exception("tracker crashed: %s", type(exc).__name__)
        try:
            tracker.deliver(f"🛑 *Stock bot crashed* ({type(exc).__name__}). Restarting.", "Stock bot crashed")
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
