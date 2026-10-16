"""Human-readable messages.

Messages are written once in WhatsApp markup (*bold*, _italic_) and converted
for each channel: Telegram gets escaped HTML (the old code sent **bold** with
legacy Markdown, which broke formatting and made some alerts fail to send),
Discord gets **bold**, email gets plain text.
"""

from __future__ import annotations

import html
import re
from typing import Optional

from .signals import (
    EARNINGS_BLOCK, EVENT_BLOCK, NO_DATA, NO_TREND, REGIME_BLOCK, SECTOR_BLOCK, SETUP, SIGNAL, Signal,
)

DISCLAIMER = "_Educational only – not financial advice._"

_BOLD = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_ITAL = re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")


def to_telegram_html(text: str) -> str:
    out = html.escape(text, quote=False)
    out = _BOLD.sub(r"<b>\1</b>", out)
    return _ITAL.sub(r"<i>\1</i>", out)


def to_discord(text: str) -> str:
    return _BOLD.sub(r"**\1**", text)


def to_plain(text: str) -> str:
    return _ITAL.sub(r"\1", _BOLD.sub(r"\1", text))


def split_message(text: str, limit: int) -> list[str]:
    """Split on line boundaries into chunks no longer than `limit`."""
    chunks, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:  # pathological long line
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) > limit:
            chunks.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        chunks.append(cur)
    return [c.rstrip("\n") for c in chunks if c.strip()]


def _money(x: Optional[float]) -> str:
    return "n/a" if x is None else f"${x:,.2f}"


def _pct(a: float, b: float) -> str:
    return f"{(a / b - 1) * 100:+.1f}%"


ICON = {SIGNAL: "🚨", SETUP: "⏳", EARNINGS_BLOCK: "📅", EVENT_BLOCK: "🗓️", REGIME_BLOCK: "🛑",
        SECTOR_BLOCK: "🧯", NO_TREND: "⚪", NO_DATA: "❔"}


def signal_message(sig: Signal, include_quality: bool = True) -> str:
    dir_icon = {"CALL": "📞", "PUT": "📉"}.get(sig.direction or "", "")
    lines = [f"{ICON.get(sig.status, '')}{dir_icon} *{sig.symbol} – {sig.headline}*"]
    if sig.price is not None:
        lines.append(f"{_money(sig.price)} · as of {sig.asof:%a %b %d}")

    if sig.status == NO_DATA:
        lines += [f"⚠️ {w}" for w in sig.warnings]
        return "\n".join(lines)

    gates = [c for c in sig.checks if c.kind in ("gate", "trigger")]
    if gates:
        lines += ["", "*Checks*"]
        lines += [f"{'✅' if c.passed else '❌'} {c.name}: {c.detail}" for c in gates]

    quality = [c for c in sig.checks if c.kind == "quality"]
    if include_quality and quality:
        got = sum(c.passed for c in quality)
        lines += ["", f"*Quality {got}/{len(quality)}*"]
        lines += [f"{'✓' if c.passed else '✗'} {c.name}" for c in quality]

    if sig.plan:
        p = sig.plan
        lines += ["", "*Plan (underlying stock)*",
                  f"Entry ≈ {_money(p.entry)}",
                  f"Stop {_money(p.stop)} ({p.stop_pct:+.1f}%, {p.stop_basis})",
                  f"Target {p.target_r:g}R {_money(p.target)} ({_pct(p.target, p.entry)})"
                  + " · " + " · ".join(f"{r:g}R {_money(px)}" for r, px in p.targets if r != p.target_r),
                  f"Time stop: {p.max_hold_bars} trading days"]
        if p.shares is not None:
            lines.append(f"Size: {p.shares} shares ≈ {_money(p.risk_dollars)} at risk")
        lines.append(f"Options: the stock closing beyond {_money(p.stop)} is the invalidation; "
                     f"pick an expiry well past the {p.max_hold_bars}-day hold.")
        lines += [f"⚠️ {n}" for n in p.notes]

    lv = sig.levels
    if lv and (lv.resistance or lv.support) and sig.status != SIGNAL:
        lines += ["", "*Levels*"]
        if lv.resistance:
            lines.append("Resistance: " + ", ".join(_money(x) for x in lv.resistance))
        if lv.support:
            lines.append("Support: " + ", ".join(_money(x) for x in lv.support))

    if sig.warnings:
        lines += [""] + [f"⚠️ {w}" for w in sig.warnings]
    lines += ["", DISCLAIMER]
    return "\n".join(lines)
