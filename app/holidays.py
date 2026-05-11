"""Seasonal holiday detection for the display overlay.

Returns the active holiday key for a given date, or ``None`` if no holiday
matches. The display template uses the key to pick a Twemoji SVG from
``static/img/holidays/<key>.svg``.

Date windows are deliberately a few days wide so the icon can appear in
the lead-up to the holiday rather than only on the day itself.
"""
from __future__ import annotations

import datetime as dt


HOLIDAY_LABELS: dict[str, str] = {
    "xmas":         "Christmas",
    "new-years":    "New Year's Eve",
    "valentines":   "Valentine's Day",
    "st-patricks":  "St Patrick's Day",
    "april-fools":  "April Fools' Day",
    "easter":       "Easter",
    "july-4":       "4th of July",
    "halloween":    "Halloween",
    "thanksgiving": "Thanksgiving",
}


def _compute_easter(year: int) -> dt.date:
    """Easter Sunday in the Gregorian calendar (Anonymous Gregorian algorithm)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def _thanksgiving(year: int) -> dt.date:
    """4th Thursday of November (US Thanksgiving)."""
    first = dt.date(year, 11, 1)
    # weekday(): Monday=0 .. Sunday=6. Thursday=3.
    days_to_first_thu = (3 - first.weekday()) % 7
    first_thu = first + dt.timedelta(days=days_to_first_thu)
    return first_thu + dt.timedelta(weeks=3)


def _in_range(today: dt.date, start: dt.date, end: dt.date) -> bool:
    return start <= today <= end


def active_holiday(today: dt.date | None = None) -> str | None:
    """Return the active holiday key for ``today`` (defaults to today).

    Fixed-date windows live in a list; computed dates (Easter, Thanksgiving)
    are appended below. Earlier list entries win when ranges overlap.
    """
    today = today or dt.date.today()
    y = today.year

    # (key, start_date, end_date)
    candidates: list[tuple[str, dt.date, dt.date]] = [
        # Christmas Dec 20 – Dec 26
        ("xmas",        dt.date(y, 12, 20), dt.date(y, 12, 26)),
        # New Year's Eve Dec 27 (this year) – Jan 2 (next year).
        # Handle the year wrap: also include the early-January window.
        ("new-years",   dt.date(y, 12, 27), dt.date(y, 12, 31)),
        ("new-years",   dt.date(y, 1, 1),   dt.date(y, 1, 2)),
        # Valentine's Day Feb 13 – 15
        ("valentines",  dt.date(y, 2, 13),  dt.date(y, 2, 15)),
        # St Patrick's Day Mar 16 – 18
        ("st-patricks", dt.date(y, 3, 16),  dt.date(y, 3, 18)),
        # April Fools Mar 31 – Apr 2
        ("april-fools", dt.date(y, 3, 31),  dt.date(y, 4, 2)),
        # 4th of July Jul 3 – Jul 5
        ("july-4",      dt.date(y, 7, 3),   dt.date(y, 7, 5)),
        # Halloween Oct 30 – Nov 1
        ("halloween",   dt.date(y, 10, 30), dt.date(y, 11, 1)),
    ]

    # Easter: Good Friday through Easter Monday.
    easter_sunday = _compute_easter(y)
    candidates.append((
        "easter",
        easter_sunday - dt.timedelta(days=2),
        easter_sunday + dt.timedelta(days=1),
    ))

    # Thanksgiving: 4th Thursday of November ± 1 day.
    thanksgiving = _thanksgiving(y)
    candidates.append((
        "thanksgiving",
        thanksgiving - dt.timedelta(days=1),
        thanksgiving + dt.timedelta(days=1),
    ))

    for key, start, end in candidates:
        if _in_range(today, start, end):
            return key
    return None
