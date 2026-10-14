"""
Economic calendar filter using the free ForexFactory weekly JSON feed.
Blocks new signals around high-impact USD events and lists what's coming up.
"""
from datetime import datetime, timedelta, timezone

import requests

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def fetch_events(currencies=("USD",), impacts=("High",)):
    """Return (events, error). events: list of dicts with 'time' (UTC datetime)."""
    try:
        r = requests.get(FEED, timeout=15, headers={"User-Agent": "xauusd-signals"})
        r.raise_for_status()
        raw = r.json()
    except Exception as e:  # network/feed problem
        return [], f"calendar unavailable ({e.__class__.__name__})"
    events = []
    for ev in raw:
        if ev.get("country") not in currencies or ev.get("impact") not in impacts:
            continue
        try:
            t = datetime.fromisoformat(ev["date"]).astimezone(timezone.utc)
        except Exception:
            continue
        events.append({
            "title": ev.get("title", "?"),
            "currency": ev.get("country"),
            "impact": ev.get("impact"),
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
            "time": t,
        })
    events.sort(key=lambda e: e["time"])
    return events, None


def blackout(events, now, before_min=30, after_min=30):
    """Return the event causing a blackout right now, or None."""
    for ev in events:
        if ev["time"] - timedelta(minutes=before_min) <= now <= ev["time"] + timedelta(minutes=after_min):
            return ev
    return None


def upcoming(events, now, hours=24):
    return [e for e in events if now <= e["time"] <= now + timedelta(hours=hours)]
