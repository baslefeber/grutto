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
    """What the runner told us, as opposed to what the watch recorded.

    Pain is not a yes or no. A two out of ten that only shows up at the end of
    a run and a six that wakes you up are different problems with different
    answers, and a coach who treats them the same is no use to either runner.
    """
    pain: str = ""              # free text, empty means none reported
    pain_area: str = ""
    pain_score: int | None = None        # 0 to 10, None means not asked yet
    pain_when_walking: bool | None = None
    pain_worse_in_morning: bool | None = None
    pain_direction: str = ""             # better, same or worse
    days_off: int = 0
    max_hr: int | None = None
    vo2_max: float | None = None
    age: int | None = None
    goal_race: str = ""
    goal_race_date: str = ""
    notes: str = ""

    @property
    def in_pain(self):
        return bool(self.pain.strip())

    @property
    def pain_detail_known(self):
        """Have we actually asked how bad it is, or are we guessing?"""
        return self.pain_score is not None and self.pain_when_walking is not None

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


def pain_questions(st):
    """What a physio would ask before saying anything.

    Returned when someone reports pain but we do not yet know how bad it is.
    Answering these changes the advice, so guessing instead of asking is the
    worst of the available options.
    """
    missing = []
    if st.pain_score is None:
        missing.append("Out of ten, how bad is it when it is at its worst?")
    if st.pain_when_walking is None:
        missing.append("Does it hurt when you walk normally, or only when you run?")
    if st.pain_worse_in_morning is None:
        missing.append("Is it worse for the first few steps in the morning?")
    if not st.pain_direction:
        missing.append("Over the last few days, is it getting better, worse, or "
                       "staying the same?")
    return {
        "need_to_ask": bool(missing),
        "questions": missing,
        "why": ("Pain that stops you walking, or that is worse on the first steps "
                "of the morning, or that is getting worse, is a different problem "
                "from a niggle that only shows up late in a run."),
    }


def pain_severity(st):
    """How seriously to take what was reported.

    Deliberately conservative about the things that matter (morning pain,
    pain while walking, pain getting worse) and relaxed about a low score that
    only appears under load.
    """
    if not st.in_pain:
        return {"level": "none"}
    if not st.pain_detail_known:
        return {"level": "unknown", "reason": "nobody has asked how bad it is yet"}

    red = []
    if st.pain_when_walking:
        red.append("it hurts while walking")
    if st.pain_worse_in_morning:
        red.append("it is worse on the first steps of the morning")
    if st.pain_direction == "worse":
        red.append("it is getting worse")
    if (st.pain_score or 0) >= 5:
        red.append(f"it is {st.pain_score} out of ten")

    if red:
        level = "stop"
    elif (st.pain_score or 0) >= 3:
        level = "careful"
    else:
        level = "minor"

    return {
        "level": level,
        "score_out_of_ten": st.pain_score,
        "hurts_walking": st.pain_when_walking,
        "worse_in_morning": st.pain_worse_in_morning,
        "direction": st.pain_direction,
        "concerns": red,
    }


def aerobic_fitness(runs, vo2_max=None, age=None):
    """Can the engine cover the distance, separately from whether the legs can.

    These are two different questions and answering them as one is how a coach
    tells a fit runner they are unfit. VO2 max says what the cardiovascular
    system can sustain. It says nothing about what the feet will tolerate.
    """
    if not vo2_max:
        return {"known": False}

    # Rough conversions from the Daniels VDOT tables. Good enough to answer
    # "is the engine the limiting factor", which is all this is for.
    if vo2_max >= 60:   half, band = "1:25", "strong"
    elif vo2_max >= 55: half, band = "1:32", "strong"
    elif vo2_max >= 50: half, band = "1:40", "solid"
    elif vo2_max >= 45: half, band = "1:50", "adequate"
    elif vo2_max >= 40: half, band = "2:02", "modest"
    else:               half, band = "2:15+", "limited"

    return {
        "known": True,
        "vo2_max": vo2_max,
        "band": band,
        "rough_half_marathon_time": half,
        "verdict": ("The engine is not what limits you here."
                    if vo2_max >= 48 else
                    "The engine is part of what limits you here."),
    }


def durability(runs, race_distance_km):
    """Whether the legs have been this far, separately from the engine.

    Aerobic fitness carries you a long way past your longest run. Tissue does
    not, and the gap between the two is where people get hurt in races.
    """
    longest = max((r["distance_m"] / 1000.0 for r in runs), default=0)
    if not longest:
        return {"known": False}
    gap = (race_distance_km - longest) / longest * 100
    if gap <= 0:      level = "covered"
    elif gap <= 20:   level = "a stretch"
    elif gap <= 40:   level = "a big stretch"
    else:             level = "well beyond"
    return {
        "known": True,
        "longest_ever_km": round(longest, 1),
        "race_km": race_distance_km,
        "further_by_pct": round(gap, 0),
        "level": level,
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


def race_readiness(runs, race_distance_km, weeks_to_race, in_pain, days_off,
                   state=None, vo2_max=None):
    """Should this runner start this race?

    Three separate questions, answered separately, because they have different
    answers. Can the engine do it. Have the legs been this far. Is anything
    currently hurt. A runner can be aerobically ready, structurally short, and
    injured all at once, and lumping those together gives useless advice.
    """
    st = state or _state
    aero = aerobic_fitness(runs, vo2_max or st.vo2_max, st.age)
    dur = durability(runs, race_distance_km)
    pain = pain_severity(st)
    ask = pain_questions(st) if in_pain else {"need_to_ask": False, "questions": []}

    problems, notes = [], []

    if aero.get("known"):
        if aero["vo2_max"] >= 48:
            notes.append(f"Aerobically you are fine. Your fitness is around a "
                         f"{aero['rough_half_marathon_time']} half marathon, and it "
                         f"has been rising.")
        else:
            problems.append("Your aerobic fitness is short of this distance.")

    if dur.get("known") and dur["level"] != "covered":
        line = (f"The furthest you have ever run is {dur['longest_ever_km']} km and "
                f"the race is {race_distance_km:.0f} km, {dur['further_by_pct']:.0f}% "
                f"further.")
        if dur["level"] == "a stretch":
            notes.append(line + " That is a normal race day stretch.")
        else:
            problems.append(line)

    if ask["need_to_ask"]:
        return {
            "call": "need to know more first",
            "must_ask": ask["questions"],
            "why_asking": ask["why"],
            "aerobic": aero, "durability": dur,
            "weeks_to_race": weeks_to_race,
        }

    if pain["level"] == "stop":
        problems.append("The pain needs seeing before the race is a question: "
                        + ", ".join(pain["concerns"]) + ".")
    elif pain["level"] == "careful":
        notes.append("The pain is real but mild. A test run decides this, not a guess.")
    elif pain["level"] == "minor":
        notes.append("The pain is minor and only shows up under load.")

    if days_off >= 7 and pain["level"] in ("stop", "unknown"):
        problems.append(f"You have not run for {days_off} days.")

    # the call
    if pain["level"] == "stop":
        call = "do not race it"
    elif not problems and pain["level"] in ("none", "minor"):
        call = "race it"
    elif dur.get("level") in ("a big stretch", "well beyond") or problems:
        call = ("run it, but as a long run rather than a race, and be ready to stop"
                if pain["level"] in ("none", "minor", "careful") and aero.get("vo2_max", 0) >= 48
                else "do not race it")
    else:
        call = "race it, conservatively"

    return {
        "call": call,
        "aerobic": aero,
        "durability": dur,
        "pain": pain,
        "race_km": race_distance_km,
        "weeks_to_race": weeks_to_race,
        "problems": problems,
        "in_your_favour": notes,
        "alternatives": [
            "Drop to a shorter distance at the same event if there is one.",
            "Defer to a race eight to twelve weeks out and build to it properly.",
        ] if call == "do not race it" else [],
    }
