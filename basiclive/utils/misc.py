from __future__ import annotations

from datetime import timedelta, datetime, date
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime


def humanize_duration(duration, sec=False):
    if isinstance(duration, (int, float)):
        return natural_seconds(timedelta(hours=duration).total_seconds())
    return natural_seconds(duration.total_seconds())


def natural_seconds(seconds, depth=2):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    weeks, days = divmod(days, 7)
    months, weeks = divmod(weeks, 4.35)
    years, months = divmod(months, 12)

    units = ['year', 'month', 'week', 'day', 'hour', 'min', 'sec']
    values = [years, months, weeks, days, hours, minutes, seconds]
    entries = [
        f'{val:0.0f} {unit}{"s" if val > 1 else ""}'
        for val, unit in zip(values, units) if round(val) > 0
    ]

    return ' '.join(entries[:depth]) or '0 minutes'


def natural_duration(delta):
    if isinstance(delta, datetime):
        delta = timezone.now() - delta
    return natural_seconds(delta.total_seconds())


def parse_date_value(val: Any) -> date | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    parsed_d = parse_date(s[:10])
    if parsed_d:
        return parsed_d
    parsed_dt = parse_datetime(s)
    if parsed_dt:
        return parsed_dt.date()
    return None


class NestedDict:
    """
    Wraps a nested dictionary and supports retrieving nested values using either dot notation or double-underscore
    notation.
    """

    def __init__(self, data: dict):
        self._data = data

    def _resolve_key(self, key: str):
        # Normalize both '__' and '.' into a common list of key parts
        parts = key.replace('__', '.').split('.')

        current = self._data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                # Return None if the key or path doesn't exist
                return None
        return current

    def __getattr__(self, name: str):
        # Intercepts attribute access like obj.missing_key
        val = self._resolve_key(name)
        if isinstance(val, dict):
            return NestedDict(val)
        return val

    def __getitem__(self, key: str):
        # Allows bracket access like obj['missing_key']
        val = self._resolve_key(key)
        if isinstance(val, dict):
            return NestedDict(val)
        return val

    def __repr__(self):
        return f"NestedDict({self._data!r})"
