"""Noticing that something happened, without being asked.

A coach who only speaks when spoken to is a search box. The two moments that
matter are the start of a week, when the plan is written, and the hour after a
run, when what actually happened is still worth saying something about.

This holds the small amount of state needed to know whether either has
happened since last time. It is deliberately dumb: no scheduling, no daemon.
Something outside calls it. A cron line, a launchd job, a Lambda on a timer.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

STATE = Path(__file__).resolve().parent.parent / ".watcher.json"


def _load():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except json.JSONDecodeError:
            pass
    return {"seen_runs": [], "last_weekly": None}


def _save(d):
    STATE.write_text(json.dumps(d, indent=2))
    return d


def reset():
    return _save({"seen_runs": [], "last_weekly": None})


def unreviewed_runs(runs):
    """Runs that have appeared since the last time anyone looked."""
    seen = set(_load()["seen_runs"])
    return [r for r in runs if f"{r['date']}|{r['distance_m']:.0f}" not in seen]


def mark_reviewed(runs):
    d = _load()
    d["seen_runs"] = sorted(set(d["seen_runs"])
                            | {f"{r['date']}|{r['distance_m']:.0f}" for r in runs})
    return _save(d)


def weekly_due(today=None):
    """Has this week's plan been written yet?

    The running week starts on Monday. If the plan for the current week has not
    been written, it is due, whatever day it is now.
    """
    today = today or date.today()
    if isinstance(today, str):
        y, m, dd = (int(x) for x in today.split("-"))
        today = date(y, m, dd)
    monday = (today - timedelta(days=today.weekday())).isoformat()
    return _load()["last_weekly"] != monday, monday


def mark_weekly_done(monday):
    d = _load()
    d["last_weekly"] = monday
    return _save(d)
