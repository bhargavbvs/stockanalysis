"""NYSE trading calendar (holidays and early closes).

Source: nyse.com/markets/hours-calendars (checked Oct 2026). Extend the sets
below when NYSE publishes later years; `covered_until()` lets the bot warn
before the list runs out.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

NYSE_HOLIDAYS = frozenset({
    # 2026
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
    date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
})
EARLY_CLOSES = {date(2026, 11, 27): (13, 0), date(2026, 12, 24): (13, 0), date(2027, 11, 26): (13, 0)}

SESSION = pd.offsets.CustomBusinessDay(holidays=sorted(NYSE_HOLIDAYS))


def covered_until() -> date:
    return date(max(d.year for d in NYSE_HOLIDAYS), 12, 31)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def next_session(d: date) -> date:
    return (pd.Timestamp(d) + SESSION).date()


def prev_session(d: date) -> date:
    return (pd.Timestamp(d) - SESSION).date()


def close_time(d: date) -> tuple[int, int]:
    return EARLY_CLOSES.get(d, (16, 0))
