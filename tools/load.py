"""Training load analysis.

Plain arithmetic. No model calls. The agents read these numbers and explain
them; they never work them out themselves.

Two things this does that a watch does not:

1. It counts weeks you did not run. A watch computes load from heart rate, so
   a week with no runs simply contributes nothing. Here an empty week drags
   the four-week average down, which is the honest picture: ten days off means
   you cannot pick up where you left off.

2. It ratios DISTANCE, not heart rate. Tendons, fascia and bone respond to how
   many times the foot lands, not to how hard the heart works. A runner who
   holds the same effort while doubling the mileage looks steady to a
   heart-rate model and is not.

The acute:chronic ratio is a heuristic, not a law. It comes from team-sport
research measured in session-RPE, and the running evidence is thinner than the
popular version suggests. It is used here as one input among several, and the
chronic window deliberately EXCLUDES the current week, because including it
puts the acute week inside its own denominator and flattens real spikes.
"""

from collections import defaultdict
from datetime import date, timedelta

HIGH = 1.5
CAUTION = 1.3
LONG_RUN_SHARE_MAX = 0.35


def _monday(d):
    return d - timedelta(days=d.weekday())


def _date(s):
    y, m, dd = (int(x) for x in s.split("-"))
    return date(y, m, dd)


def weekly_volume(runs, today=None):
    """Kilometres per week, oldest first, continuing to THIS week.

    Weeks with no running are included as zero. This matters: a watch that
    only sees sessions cannot tell the difference between "resting" and
    "nothing happened".
    """
    buckets = defaultdict(float)
    for r in runs:
        buckets[_monday(_date(r["date"]))] += r["distance_m"] / 1000.0

    if not buckets:
        return []

    today = _date(today) if isinstance(today, str) else (today or date.today())
    cur, last = min(buckets), max(_monday(today), max(buckets))

    weeks = []
    while cur <= last:
        weeks.append({"week_starting": cur.isoformat(), "km": round(buckets[cur], 2)})
        cur += timedelta(days=7)
    return weeks


def days_since_last_run(runs, today=None):
    if not runs:
        return None
    today = _date(today) if isinstance(today, str) else (today or date.today())
    return (today - max(_date(r["date"]) for r in runs)).days


def chronic_km(runs, today=None, weeks_back=4, exclude_current=True):
    """Average weekly kilometres over the recent past.

    The current week is left out by default so that this week's own volume
    does not inflate the baseline it is being judged against.
    """
    weeks = weekly_volume(runs, today)
    if not weeks:
        return 0.0
    window = weeks[:-1] if exclude_current and len(weeks) > 1 else weeks
    window = window[-weeks_back:]
    return round(sum(w["km"] for w in window) / max(len(window), 1), 2)


def acwr_series(runs, today=None, weeks_back=4):
    """Ratio of each week's distance to the four weeks before it.

    The current week is left out. It has not finished, so its total is not a
    total, and reporting a Monday morning as "very low" is noise.
    """
    weeks = weekly_volume(runs, today)
    this_monday = _monday(_date(today) if isinstance(today, str)
                          else (today or date.today())).isoformat()
    out = []
    for i, w in enumerate(weeks):
        if w["week_starting"] >= this_monday:
            continue
        window = weeks[max(0, i - weeks_back):i]
        if len(window) < 2:
            continue
        chronic = sum(x["km"] for x in window) / len(window)
        if chronic == 0:
            continue
        ratio = w["km"] / chronic
        flag = ("high" if ratio >= HIGH else
                "caution" if ratio >= CAUTION else
                "very low" if ratio <= 0.5 else "ok")
        out.append({
            "week_starting": w["week_starting"],
            "km": w["km"],
            "average_of_previous_4_weeks": round(chronic, 2),
            "ratio": round(ratio, 2),
            "flag": flag,
        })
    return out


def long_run_share(runs, today=None):
    """Biggest single run as a share of its own week.

    A long run that is most of the week is a common way to get hurt, and it is
    invisible to any weekly total.
    """
    by_week = defaultdict(list)
    for r in runs:
        by_week[_monday(_date(r["date"])).isoformat()].append(r["distance_m"] / 1000.0)

    out = []
    for wk in sorted(by_week):
        ds = by_week[wk]
        total = sum(ds)
        if total <= 0:
            continue
        out.append({
            "week_starting": wk,
            "longest_km": round(max(ds), 2),
            "week_km": round(total, 2),
            "share": round(max(ds) / total, 2),
            "too_big": max(ds) / total > LONG_RUN_SHARE_MAX and total > 8,
        })
    return out


def longest_run_jumps(runs):
    """How fast the longest run has been growing.

    Tissue tolerates a longer run badly when it arrives suddenly, regardless of
    what the weekly total did.
    """
    ordered = sorted(runs, key=lambda r: r["date"])
    best, out = 0.0, []
    for r in ordered:
        km = r["distance_m"] / 1000.0
        if km > best:
            if best > 0:
                out.append({
                    "date": r["date"],
                    "km": round(km, 2),
                    "previous_longest_km": round(best, 2),
                    "increase_pct": round((km - best) / best * 100, 1),
                    "big_jump": (km - best) / best > 0.20,
                })
            best = km
    return out


def ramp_check(runs, proposed_week_km, today=None, days_off=None):
    """Would this week be too big a step up? The safety officer's veto tool.

    Counts time off. A runner returning after a layoff is judged against a
    baseline that already includes the empty weeks, and a long layoff caps the
    first week back regardless of what the ratio says.
    """
    chronic = chronic_km(runs, today)
    off = days_since_last_run(runs, today) if days_off is None else days_off

    if chronic == 0:
        return {"verdict": "reject", "reason": "no recent running to build from",
                "average_of_previous_4_weeks": 0.0, "ceiling_km": 0.0}

    ratio = proposed_week_km / chronic
    ceiling = round(chronic * CAUTION, 1)
    reasons = []

    # Coming back from time off, the first week is capped harder than the
    # ratio alone would allow, whatever is proposed.
    if off is not None and off >= 7:
        ceiling = min(ceiling, round(min(chronic * 0.6, 12.0), 1))

    if ratio >= HIGH:
        verdict = "reject"
        reasons.append(f"{proposed_week_km:.0f} km is {ratio:.1f} times the "
                       f"{chronic:.1f} km average of the last four weeks")
    elif ratio >= CAUTION:
        verdict = "caution"
        reasons.append(f"{proposed_week_km:.0f} km is {ratio:.1f} times the recent average")
    else:
        verdict = "approve"

    # coming back from a layoff, the first week is capped harder than the ratio
    if off is not None and off >= 7 and proposed_week_km > ceiling:
        verdict = "reject"
        reasons.append(f"first week back after {off} days off should be "
                       f"at most about {ceiling:.0f} km")

    return {
        "verdict": verdict,
        "proposed_km": round(proposed_week_km, 2),
        "average_of_previous_4_weeks": chronic,
        "ratio": round(ratio, 2),
        "ceiling_km": ceiling,
        "days_since_last_run": off,
        "reason": "; ".join(reasons) if reasons else "within a normal step up",
    }
