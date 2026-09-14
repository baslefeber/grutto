"""The runner, not just their runs.

A watch sees sessions. It does not know you are sore, it does not know how
long you have been running, and it cannot tell an easy run from a hard one
that happened to be slow.

This module holds the things a coach asks before writing anything, plus the
one rule that matters most: if something hurts, the answer is not a smaller
training week. It is a different kind of week.
"""

from dataclasses import dataclass, field
from statistics import mean

# Easy running should sit under roughly three quarters of maximum heart rate.
# Above that it is moderate, and moderate every day is how runners end up with
# no easy days at all.
EASY_CEILING = 0.75
MODERATE_CEILING = 0.85


@dataclass
class AthleteState:
    """What the runner told us, as opposed to what the watch recorded."""
    pain: str = ""              # free text, empty means none reported
    pain_area: str = ""
    days_off: int = 0
    max_hr: int | None = None
    age: int | None = None
    goal_race: str = ""
    goal_race_date: str = ""
    notes: str = ""

    @property
    def in_pain(self):
        return bool(self.pain.strip())

    def as_dict(self):
        return {**self.__dict__, "in_pain": self.in_pain}


_state = AthleteState()


def set_state(**kw):
    global _state
    _state = AthleteState(**{k: v for k, v in kw.items() if v not in (None, "")})
    return _state


def state():
    return _state


def estimated_max_hr(runs, age=None):
    """Highest heart rate actually seen, or an age estimate if that is higher.

    The observed maximum is the better number when it exists, because an age
    formula is a population average and the runner is one person.
    """
    seen = [r.get("max_hr") or r.get("avg_hr") or 0 for r in runs]
    observed = max(seen) if seen else 0
    estimate = (208 - 0.7 * age) if age else 0
    return int(max(observed, estimate)) or None


def intensity_mix(runs, max_hr=None, age=None):
    """How much of this runner's running is actually easy.

    The most common reason a beginner gets hurt is not one hard session. It is
    that every session is moderately hard, so nothing is ever recovered from.
    """
    max_hr = max_hr or estimated_max_hr(runs, age)
    withhr = [r for r in runs if r.get("avg_hr")]
    if not max_hr or not withhr:
        return {"verdict": "unknown", "reason": "no heart rate recorded"}

    easy = [r for r in withhr if r["avg_hr"] < max_hr * EASY_CEILING]
    moderate = [r for r in withhr
                if max_hr * EASY_CEILING <= r["avg_hr"] < max_hr * MODERATE_CEILING]
    hard = [r for r in withhr if r["avg_hr"] >= max_hr * MODERATE_CEILING]

    easy_share = len(easy) / len(withhr)
    if easy_share < 0.3:
        verdict = "almost nothing is easy"
    elif easy_share < 0.6:
        verdict = "not enough easy running"
    else:
        verdict = "reasonable spread"

    return {
        "verdict": verdict,
        "max_hr_used": max_hr,
        "runs_with_hr": len(withhr),
        "easy_runs": len(easy),
        "moderate_runs": len(moderate),
        "hard_runs": len(hard),
        "easy_share": round(easy_share, 2),
        "easy_hr_ceiling": int(max_hr * EASY_CEILING),
        "average_hr_on_all_runs": round(mean(r["avg_hr"] for r in withhr)),
    }


def return_to_run_plan(days_off, area=""):
    """What to do when something hurts. Not a training week.

    This is deliberately not a scaled-down version of a normal week. Returning
    from pain is a different exercise: test whether it hurts, at all, before
    doing anything that resembles training.
    """
    where = f" in your {area}" if area else ""
    return {
        "kind": "return_to_run",
        "running_this_week": False,
        "see_someone": (
            f"Pain{where} that stopped you running for {days_off} days is worth "
            "having a physiotherapist look at before you run on it again. That is "
            "the first step, not the last one."
        ),
        "steps": [
            "Walk 30 minutes on the flat. If that hurts at all, or hurts "
            "afterwards, stop here and see a physio.",
            "Two days later, if walking was clean: 10 minutes very easy jogging. "
            "Any pain during or the next morning means stop.",
            "Two days after that, if that was clean: 20 minutes very easy.",
            "Only once you have done that without pain does a normal week start, "
            "and it starts small.",
        ],
        "hard_rule": (
            "Pain that gets worse as you run, or that is still there the next "
            "morning, means stop and get it looked at. Do not run through it."
        ),
    }


def race_readiness(runs, race_distance_km, weeks_to_race, in_pain, days_off):
    """Should this runner start this race?

    A judgement a watch will never make, and the one that matters most to
    someone with an entry already paid for.
    """
    longest = max((r["distance_m"] / 1000.0 for r in runs), default=0)
    gap = (race_distance_km - longest) / longest * 100 if longest else 999
    problems = []

    if in_pain or days_off >= 7:
        problems.append(
            f"You have not run for {days_off} days because something hurts. "
            "That has to be resolved before the race is even a question."
        )
    if race_distance_km > longest:
        problems.append(
            f"The race is {race_distance_km:.0f} km. The furthest you have ever "
            f"run is {longest:.1f} km, which is {gap:.0f}% short."
        )
    if weeks_to_race <= 3 and (in_pain or days_off >= 7):
        problems.append(
            f"With {weeks_to_race} weeks left there is not enough time to come "
            "back from this and build up safely."
        )

    if not problems:
        call = "race"
    elif len(problems) == 1 and race_distance_km <= longest * 1.15:
        call = "start, but treat it as a long run rather than a race"
    else:
        call = "do not race it"

    return {
        "call": call,
        "longest_ever_km": round(longest, 1),
        "race_km": race_distance_km,
        "weeks_to_race": weeks_to_race,
        "problems": problems,
        "alternatives": [
            "Drop to a shorter distance at the same event if there is one.",
            "Defer to a race eight to twelve weeks out and build to it properly.",
        ] if call == "do not race it" else [],
    }
