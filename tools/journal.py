"""What the runner told us, kept between conversations.

A watch has your runs. It does not have the fact that you said your feet hurt
on a Monday in September, that you were told not to race, or that you were
given 16 km and ran 32.

That last one is the whole reason this exists. A coach who cannot remember what
they asked you to do cannot tell whether you did it, and a coach who cannot
tell that has no way to learn anything about you.

Stored as plain JSON so you can read it, edit it, or delete it.
"""

import json
from datetime import date, datetime
from pathlib import Path

JOURNAL = Path(__file__).resolve().parent.parent / "journal.json"

EMPTY = {
    "runner": {},
    "events": [],   # things the runner said or was told
    "plans": [],    # weeks that were written, approved or refused
}


def _load():
    if JOURNAL.exists():
        try:
            return json.loads(JOURNAL.read_text())
        except json.JSONDecodeError:
            pass
    return json.loads(json.dumps(EMPTY))


def _save(d):
    JOURNAL.write_text(json.dumps(d, indent=2))
    return d


def reset():
    return _save(json.loads(json.dumps(EMPTY)))


def set_runner(**fields):
    d = _load()
    d["runner"].update({k: v for k, v in fields.items() if v not in (None, "")})
    return _save(d)["runner"]


def add_event(kind, text, on=None, **data):
    """Record something worth remembering.

    kind is one of: symptom, symptom_cleared, advice, race_decision, note.
    """
    d = _load()
    d["events"].append({
        "on": on or date.today().isoformat(),
        "at": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "text": text,
        **data,
    })
    return _save(d)["events"][-1]


def add_plan(week_starting, sessions, total_km, approved, ceiling_km=None,
             refusals=None):
    d = _load()
    d["plans"].append({
        "created": datetime.now().isoformat(timespec="seconds"),
        "week_starting": week_starting,
        "sessions": sessions,
        "total_km": round(total_km, 2),
        "approved": approved,
        "ceiling_km": ceiling_km,
        "refusals": refusals or [],
    })
    return _save(d)["plans"][-1]


def open_symptoms():
    """Symptoms reported and not since marked cleared."""
    d = _load()
    open_ = {}
    for e in d["events"]:
        if e["kind"] == "symptom":
            open_[e.get("area", "unspecified")] = e
        elif e["kind"] == "symptom_cleared":
            open_.pop(e.get("area", "unspecified"), None)
    return list(open_.values())


def plan_vs_actual(runs):
    """What was planned against what was actually run.

    The single most useful thing a coach can know and the one thing a watch
    can never tell you, because a watch has no idea what you were asked to do.
    """
    from collections import defaultdict
    from datetime import timedelta

    d = _load()
    if not d["plans"]:
        return []

    by_week = defaultdict(float)
    for r in runs:
        y, m, dd = (int(x) for x in r["date"].split("-"))
        day = date(y, m, dd)
        by_week[(day - timedelta(days=day.weekday())).isoformat()] += r["distance_m"] / 1000.0

    out = []
    for p in d["plans"]:
        if not p["approved"]:
            continue
        actual = round(by_week.get(p["week_starting"], 0.0), 2)
        planned = p["total_km"]
        if actual == 0:
            continue
        out.append({
            "week_starting": p["week_starting"],
            "planned_km": planned,
            "actually_ran_km": actual,
            "difference_pct": round((actual - planned) / planned * 100, 1) if planned else None,
            "followed": abs(actual - planned) / planned < 0.2 if planned else None,
        })
    return out


def recall_pain_detail():
    """The most recent answers about how bad the pain is.

    A runner should not be asked the same four questions every time they open
    the app. They answered once; that answer holds until they say otherwise.
    """
    d = _load()
    for e in reversed(d["events"]):
        if e["kind"] == "symptom_cleared":
            return {}
        if e["kind"] == "symptom_detail":
            return {k: e[k] for k in
                    ("pain_score", "pain_when_walking", "pain_worse_in_morning",
                     "pain_direction") if e.get(k) is not None}
    return {}


def summary(runs=None):
    d = _load()
    return {
        "runner": d["runner"],
        "open_symptoms": open_symptoms(),
        "recent_events": d["events"][-8:],
        "recent_plans": [
            {k: p[k] for k in ("week_starting", "total_km", "approved", "refusals")}
            for p in d["plans"][-4:]
        ],
        "plan_vs_actual": plan_vs_actual(runs) if runs else [],
    }
