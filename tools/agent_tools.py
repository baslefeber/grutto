"""Tools the agents call.

Thin wrappers over plain arithmetic. The docstrings matter: they are what the
model reads to decide when to reach for each one.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from strands import tool

import athlete
import journal
from form import weekly_form_drift, within_run_decay
from garmin_source import get_source
from gate import gate
from load import (acwr_series, chronic_km, days_since_last_run, long_run_share,
                 longest_run_jumps, ramp_check, weekly_volume)

_source = None
TODAY = None


def source():
    global _source
    if _source is None:
        _source = get_source()
    return _source


def reset_source():
    global _source
    _source = None


def _runs():
    return source().runs()


@tool
def get_run_history() -> str:
    """Every recorded run: date, name, distance, duration and average heart rate."""
    runs = [{k: r[k] for k in ("date", "name", "distance_m", "duration_s", "avg_hr")}
            for r in _runs()]
    return json.dumps({"run_count": len(runs), "runs": runs}, indent=2)


@tool
def get_weekly_volume() -> str:
    """Kilometres run in each week, continuing up to the current week.

    Weeks with no running appear as zero. Time off counts: it pulls the recent
    average down, which is why you cannot pick up where you left off.
    """
    return json.dumps({
        "weeks": weekly_volume(_runs(), TODAY),
        "average_of_last_four_weeks": chronic_km(_runs(), TODAY),
        "days_since_last_run": days_since_last_run(_runs(), TODAY),
    }, indent=2)


@tool
def get_workload_ratio() -> str:
    """Each week's distance against the average of the four weeks before it.

    At or above 1.5 is flagged high, 1.3 is caution. This is a rule of thumb
    borrowed from team sports, not a law of nature, so treat it as one input
    rather than the answer.

    A watch computes its own version of this from heart rate. That version
    cannot see a runner who doubles their distance at the same effort. This
    one ratios distance, which is what the feet and legs actually absorb.
    """
    return json.dumps(acwr_series(_runs(), TODAY), indent=2)


@tool
def get_long_run_pattern() -> str:
    """How big the longest run is compared to its own week, and how fast the
    longest run has been growing.

    A long run that is most of the week, or one that jumps a long way past the
    previous longest, is a common way to get hurt and is invisible in a weekly
    total.
    """
    return json.dumps({
        "share_of_week": long_run_share(_runs(), TODAY),
        "new_longest_runs": longest_run_jumps(_runs()),
    }, indent=2)


@tool
def get_intensity_mix() -> str:
    """How much of this runner's running is genuinely easy.

    Check this early. The most common reason a newer runner gets hurt is not
    one hard session. It is that every session sits at a moderate effort, so
    nothing is ever properly recovered from.
    """
    st = athlete.state()
    return json.dumps(athlete.intensity_mix(_runs(), max_hr=st.max_hr, age=st.age), indent=2)


@tool
def check_proposed_week(proposed_week_km: float) -> str:
    """Test whether a proposed week is too big a step up.

    Returns approve, caution or reject, the recent average it was judged
    against, and the most this runner should do this week. Accounts for time
    off: a first week back after a layoff is capped harder than the ratio alone
    would suggest.

    Args:
        proposed_week_km: total kilometres in the proposed week.
    """
    return json.dumps(ramp_check(_runs(), proposed_week_km, TODAY), indent=2)


@tool
def get_form_trend() -> str:
    """How this runner's running is changing, comparing runs held at a similar
    speed. Reports cadence, and how the foot behaves on landing.

    Runs at different speeds are excluded, because these things change with
    pace on their own and comparing across paces says nothing.
    """
    return json.dumps(weekly_form_drift(_runs()), indent=2)


@tool
def get_within_run_decay(run_date: str) -> str:
    """Whether the runner held together through one particular run.

    Reports the cadence trend across kilometres and how much harder the heart
    was working for the same speed by the second half. This measures how
    durable their fitness is. It does not measure injury risk.

    Args:
        run_date: date of the run, YYYY-MM-DD.
    """
    laps = source().laps(run_date)
    if not laps:
        return json.dumps({"error": f"No kilometre splits recorded for {run_date}."})
    return json.dumps(within_run_decay(laps), indent=2)


@tool
def get_athlete_state() -> str:
    """What the runner has told us, as opposed to what the watch recorded.

    Whether anything hurts, where, how long they have been off, and what they
    are training for. ALWAYS check this first. A watch cannot know someone is
    in pain, and nothing else in this system can either.
    """
    return json.dumps(athlete.state().as_dict(), indent=2)


@tool
def get_return_to_run_plan() -> str:
    """What to do when something hurts. This is not a smaller training week.

    Use this instead of a training plan whenever the runner has reported pain.
    It is a sequence of tests: walk, then jog briefly, then slightly longer,
    stopping at the first sign of pain, with a physiotherapist involved early.
    """
    st = athlete.state()
    return json.dumps(athlete.return_to_run_plan(st.days_off or 0, st.pain_area), indent=2)


@tool
def get_race_verdict(race_distance_km: float = 0.0) -> str:
    """Should this runner start their race?

    Works out how long is left from the race date on file, so never guess at
    that. Compares the distance against the furthest they have ever run, how
    long they have been out, and whether anything currently hurts.

    Args:
        race_distance_km: the race distance. Leave at 0 to use the race on file.
    """
    from datetime import date

    st = athlete.state()
    km = race_distance_km or {"half marathon": 21.1, "marathon": 42.2,
                              "10k": 10.0, "5k": 5.0}.get(st.goal_race.lower(), 0.0)
    if not km:
        return json.dumps({"error": "No race distance known."})

    days = None
    if st.goal_race_date:
        y, m, d = (int(x) for x in st.goal_race_date.split("-"))
        today = date(*[int(x) for x in TODAY.split("-")]) if TODAY else date.today()
        days = (date(y, m, d) - today).days

    out = athlete.race_readiness(_runs(), km, max(round((days or 0) / 7), 0),
                                 st.in_pain, st.days_off or 0)
    out["race_date"] = st.goal_race_date
    out["days_until_race"] = days
    return json.dumps(out, indent=2)


@tool
def publish_workout(day: str, description: str, distance_km: float,
                    approved_plan: str) -> str:
    """Send one session to the runner's watch.

    Refuses unless the safety officer approved this exact plan. The check is in
    code, not in wording, so nothing said in a conversation can get a rejected
    week through.

    Args:
        day: which day the session is for.
        description: what the session is, in a sentence.
        distance_km: distance of the session.
        approved_plan: the approved week, copied exactly as the safety officer saw it.
    """
    if not gate().allows(approved_plan):
        return json.dumps({
            "status": "refused",
            "reason": "This week was not approved by the safety check, or the text "
                      "does not match what was approved. Nothing was sent.",
        }, indent=2)
    return json.dumps(source().publish_workout({
        "day": day, "description": description, "distance_km": distance_km}), indent=2)


@tool
def get_journal() -> str:
    """What this runner has told us before, and what they were told.

    Symptoms they reported and whether those were ever marked cleared, advice
    already given, weeks that were written, and what they actually ran against
    what was planned.

    Check this before anything else alongside their current state. A coach who
    cannot remember what they asked for last week cannot tell whether it was
    followed.
    """
    return json.dumps(journal.summary(_runs()), indent=2)


@tool
def remember_symptom(area: str, description: str, when: str = "") -> str:
    """Write down that something hurts, so it is still known next time.

    Args:
        area: where it hurts, for example "both feet" or "left knee".
        description: what the runner said, in their words.
        when: the date it started, YYYY-MM-DD, if known.
    """
    return json.dumps(journal.add_event("symptom", description,
                                        on=when or None, area=area), indent=2)


@tool
def remember_symptom_cleared(area: str, note: str = "") -> str:
    """Write down that something that used to hurt no longer does.

    Args:
        area: the area that has cleared.
        note: anything worth keeping, such as a physio's verdict.
    """
    return json.dumps(journal.add_event("symptom_cleared", note or f"{area} no longer sore",
                                        area=area), indent=2)


@tool
def remember_advice(what_you_told_them: str) -> str:
    """Write down a decision or piece of advice, so it is not repeated or
    contradicted next time. Use this for race decisions and for anything you
    told the runner not to do.

    Args:
        what_you_told_them: one or two sentences.
    """
    return json.dumps(journal.add_event("advice", what_you_told_them), indent=2)


@tool
def get_pain_questions() -> str:
    """What to ask someone who has reported pain, before deciding anything.

    Call this whenever pain is reported and the detail is not already known.
    A two out of ten that only appears late in a run and a six that hurts when
    you walk are different problems with different answers. Guessing between
    them is worse than asking.
    """
    return json.dumps(athlete.pain_questions(athlete.state()), indent=2)


@tool
def remember_pain_detail(score_out_of_ten: int, hurts_when_walking: bool,
                         worse_in_morning: bool, direction: str) -> str:
    """Write down how bad the pain actually is, once the runner has told you.

    Args:
        score_out_of_ten: 0 to 10 at its worst.
        hurts_when_walking: true if normal walking hurts.
        worse_in_morning: true if the first steps of the morning are worse.
        direction: better, same or worse over the last few days.
    """
    st = athlete.state()
    athlete.set_state(**{**st.__dict__, "pain_score": score_out_of_ten,
                         "pain_when_walking": hurts_when_walking,
                         "pain_worse_in_morning": worse_in_morning,
                         "pain_direction": direction})
    journal.add_event("symptom_detail",
                      f"{score_out_of_ten}/10, walking hurts: {hurts_when_walking}, "
                      f"worse in the morning: {worse_in_morning}, getting {direction}",
                      area=st.pain_area)
    return json.dumps(athlete.pain_severity(athlete.state()), indent=2)


@tool
def get_fitness() -> str:
    """How good this runner's engine is, separately from what their legs have done.

    Aerobic fitness and structural durability are different questions with
    different answers. A runner can be aerobically ready for a distance their
    legs have never covered, and telling them they are unfit would be wrong.
    """
    st = athlete.state()
    return json.dumps({
        "aerobic": athlete.aerobic_fitness(_runs(), st.vo2_max, st.age),
        "longest_run_jumps": longest_run_jumps(_runs()),
        "oversized_long_runs": [s for s in long_run_share(_runs(), TODAY) if s["too_big"]],
    }, indent=2)
