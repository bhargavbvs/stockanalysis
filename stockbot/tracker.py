"""Long-running service: intraday scans + the daily morning brief.

Fixes over the old stock_tracker.py:
  * The brief/earnings job used schedule's server-local time ("08:00" on a UTC
    Railway box = 4am ET). Times here are explicit time zones.
  * Any exception used to end the process with exit code 0, so Railway's
    ON_FAILURE restart never kicked in. Job errors are now caught and reported;
    a crash of the loop itself exits with code 1.
  * Alert history lived in a committed alert_history.json. State now lives in
    DATA_DIR (mount a Railway volume there to keep it across deploys).
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

from . import brief as brief_mod, config, scanner
from .alerts import Notifier
from .regime import CAUTION
from .report import signal_message, to_plain
from .signals import CONFIDENCE, SETUP, SIGNAL, Signal

log = logging.getLogger("stockbot")
ET = ZoneInfo("America/New_York")
SCAN_OPEN = (9, 30)
SCAN_CLOSE = (16, 15)  # include the closing bar


def in_scan_window(now: datetime) -> bool:
    now = now.astimezone(ET)
    if now.weekday() >= 5:
        return False
    t = (now.hour, now.minute)
    return SCAN_OPEN <= t <= SCAN_CLOSE


class Tracker:
    def __init__(self, settings: config.Settings, notifier: Optional[Notifier] = None, dry_run: bool = False):
        self.s = settings
        self.notifier = notifier or Notifier(settings)
        self.dry_run = dry_run
        self.state_file = Path(settings.data_dir) / "state.json"
        self.state = self._load_state()
        self._last_error_notice: Optional[datetime] = None
        self._brief_attempts: dict[str, list[datetime]] = {}

    # ----------------------------------------------------------------- state
    def _load_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text())
        except Exception:
            return {"alerts": {}, "last_brief": None}

    def _save_state(self) -> None:
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, indent=1, sort_keys=True))
        except Exception as exc:
            log.warning("could not save state: %s", exc)

    # ---------------------------------------------------------------- output
    def deliver(self, text: str, subject: str, payload: Optional[dict] = None) -> None:
        if self.dry_run:
            print(to_plain(text), "\n" + "-" * 60)
            return
        results = self.notifier.send(text, subject, payload)
        log.info("sent '%s' -> %s", subject, results or "no channels")

    # ----------------------------------------------------------------- scans
    def should_alert(self, sig: Signal, now: datetime) -> bool:
        if sig.status != SIGNAL and not (self.s.alert_setups and sig.status == SETUP):
            return False
        need = self.s.min_confidence_rank
        regime = sig.regime
        if sig.direction == "CALL" and regime is not None and regime.available and regime.mode == CAUTION:
            need = max(need, CONFIDENCE.index("HIGH"))
        if sig.status == SIGNAL and CONFIDENCE.index(sig.confidence) < need:
            return False
        key = f"{sig.symbol}:{sig.direction}:{sig.status}"
        last = self.state["alerts"].get(key)
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
            if self.should_alert(sig, now):
                self.deliver(signal_message(sig), f"{sig.symbol} {sig.direction} {sig.status}",
                             {"symbol": sig.symbol, "status": sig.status, "direction": sig.direction,
                              "confidence": sig.confidence, "price": sig.price})
                self.state["alerts"][f"{sig.symbol}:{sig.direction}:{sig.status}"] = now.isoformat()
                sent += 1
        self._save_state()
        log.info("scan done: %d alerts (%s)", sent, ctx.regime.describe())
        return sigs

    # ----------------------------------------------------------------- brief
    def brief_due(self, now: datetime) -> bool:
        if not self.s.brief_enabled:
            return False
        local = now.astimezone(ZoneInfo(self.s.brief_tz))
        if local.strftime("%a").lower()[:3] not in self.s.brief_days:
            return False
        hh, mm = (int(x) for x in self.s.brief_time.split(":"))
        if (local.hour, local.minute) < (hh, mm):
            return False
        day = local.date().isoformat()
        if self.state.get("last_brief") == day:
            return False
        tries = self._brief_attempts.get(day, [])
        # failed attempts: retry every 20 minutes, at most 3 times a day
        return len(tries) < 3 and (not tries or now - tries[-1] >= timedelta(minutes=20))

    def send_brief(self, now: Optional[datetime] = None) -> str:
        now = now or datetime.now(ZoneInfo(self.s.brief_tz))
        text = brief_mod.build(self.s, now)
        self.deliver(text, f"Morning brief {now:%b %d}")
        self.state["last_brief"] = now.astimezone(ZoneInfo(self.s.brief_tz)).date().isoformat()
        self._save_state()
        return text

    # ------------------------------------------------------------------ loop
    def _job(self, name: str, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as exc:
            log.exception("%s failed: %s", name, exc)
            now = datetime.now(ET)
            if not self._last_error_notice or now - self._last_error_notice > timedelta(hours=6):
                self._last_error_notice = now
                self.deliver(f"⚠️ *Stock bot:* {name} failed – {type(exc).__name__}: {exc}", "Stock bot error")

    def run_forever(self) -> None:
        interval = timedelta(minutes=self.s.scan_interval_minutes)
        log.info("tracker started: %d symbols, scans every %d min (9:30–16:15 ET), brief %s %s",
                 len(self.s.scan_symbols), self.s.scan_interval_minutes, self.s.brief_time, self.s.brief_tz)
        self.deliver(f"✅ Stock bot online – watching {len(self.s.scan_symbols)} symbols, "
                     f"brief daily at {self.s.brief_time} ({self.s.brief_tz}).", "Stock bot online")
        last_scan: Optional[datetime] = None
        while True:
            now = datetime.now(ET)
            if self.brief_due(now):
                day = now.astimezone(ZoneInfo(self.s.brief_tz)).date().isoformat()
                self._brief_attempts.setdefault(day, []).append(now)
                self._job("morning brief", self.send_brief)
            if in_scan_window(now) and (last_scan is None or now - last_scan >= interval):
                last_scan = now
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
    settings = config.load(args.env)
    tracker = Tracker(settings, dry_run=args.dry_run)

    if args.test:
        tracker.deliver("✅ *Test message* from your stock bot. If you can read this, delivery works.", "Test")
        return 0
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
        log.exception("tracker crashed: %s", exc)
        try:
            tracker.deliver(f"🛑 *Stock bot crashed* – {type(exc).__name__}: {exc}. Restarting.", "Stock bot crashed")
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
