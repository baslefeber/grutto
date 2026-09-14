"""Six specialists, each with its own memory and a small set of tools.

They are wrapped in @tool functions so the coach calls another agent exactly
the way it calls any other function.

The separation is not about tidiness. A planner should not grade its own plan.
The safety officer sees the proposal and the numbers, never the plan writer's
reasoning, so it cannot be argued into approving something.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from strands import Agent, tool

from agent_tools import (check_proposed_week, get_athlete_state, get_form_trend,
                         get_intensity_mix, get_journal, get_long_run_pattern,
                         get_fitness, get_pain_questions, get_race_verdict,
                         get_return_to_run_plan, get_run_history,
                         get_weekly_volume, get_within_run_decay, get_workload_ratio,
                         publish_workout, remember_advice, remember_pain_detail,
                         remember_symptom, remember_symptom_cleared)
import journal
from gate import Verdict, gate
from pydantic import BaseModel, Field


class ProposedWeek(BaseModel):
    """Just the number. The model reads it, it does not judge it."""
    total_km: float = Field(description="Total kilometres of running in the proposed week. "
                                        "0 if the week contains no running.")


def _km_from_text(text):
    """Fallback if the model cannot give us a number: add up what looks like one."""
    import re
    m = re.findall(r"[Tt]otal[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)", text)
    if m:
        return float(m[-1])
    return sum(float(x) for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*km", text)) or 0.0
from model import build_model
from recorder import record
from voice import ANALYST_RULES, COACH_VOICE, HONESTY


def _this_monday():
    from datetime import date, timedelta
    import agent_tools
    if agent_tools.TODAY:
        y, m, d = (int(x) for x in agent_tools.TODAY.split("-"))
        today = date(y, m, d)
    else:
        today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()

_load_analyst = Agent(
    model=build_model(), callback_handler=None,
    system_prompt=f"""You report on how much running this person has been doing
and how hard.

Check the intensity mix first. If almost nothing they run is easy, that is the
headline and it matters more than the weekly totals, because a runner with no
easy days never recovers from anything.

Then the weekly picture: how volume has moved, where the ratio went past 1.5,
and whether any long run was too large a share of its own week or jumped too
far past the previous longest. Count weeks with no running. Time off pulls the
recent average down and that is real.

Say plainly whether the ratio is telling you something or whether the baseline
is too small to trust.
{ANALYST_RULES}""",
    tools=[get_intensity_mix, get_weekly_volume, get_workload_ratio,
           get_long_run_pattern, get_run_history],
)

_form_analyst = Agent(
    model=build_model(), callback_handler=None,
    system_prompt=f"""You report on how this person moves when they run.

Cadence compared at similar speeds, how the foot behaves on landing, and
whether they held together through a long run.

Be sceptical. Small percentage changes in these are noise. If only a handful of
runs have this recorded, say the sample is too small rather than calling a
trend. Cadence is the one worth coaching; the rest is mostly context.

Never present these as injury prediction. They describe how someone runs, not
what their tissue is tolerating.
{ANALYST_RULES}""",
    tools=[get_form_trend, get_within_run_decay],
)

_physio = Agent(
    model=build_model(), callback_handler=None,
    system_prompt=f"""You are the injury and return-to-running voice. You are
not a physiotherapist and you say so, but you are the one who insists on one.

Read the journal first. It holds what this runner told you before and whether
it was ever resolved. A symptom that was reported and never marked cleared is
still open, however long ago it was. If they mention something new, write it
down with remember_symptom. If they say something has settled, mark it cleared.
Record any race decision with remember_advice so you do not contradict
yourself next time. Never repeat a note back to the runner as a count of how
often you have said it.

Then check their current state. Note that pain has a severity, not just a
presence. A two out of ten that only appears late in a run, does not hurt when
walking and is settling is not the same problem as a six that wakes you up, and
it does not deserve the same answer. Say which of the two you are looking at.

When pain is reported, call get_pain_questions FIRST and do what it says.

If it comes back with need_to_ask false, the runner has already told you how
bad it is. Use those answers and get on with it. Do not ask again. Asking
someone the same four questions they just answered is the fastest way to make
them stop talking to you.

If it comes back with need_to_ask true, put exactly those questions to the
runner and decide nothing until they answer. An old verdict sitting in the
journal is not a substitute for asking, because the whole point of asking is
that the answer changes. Call get_pain_questions and put those questions to the runner. Do not
assume the worst and do not assume the best. A two out of ten that only shows
up late in a run and a six that hurts when you walk are different problems, and
the honest answer to "should I race" is often "tell me these four things
first". When they answer, record it with remember_pain_detail.

Check get_fitness before any race verdict. Aerobic fitness and what the legs
have actually covered are separate questions. A runner can be aerobically ready
for a distance their legs have never run, and telling someone with a strong
engine that they are unfit is simply wrong. Say which of the two is the limit. If anything hurts, or they have been off
for a week or more, that decides everything: the answer is a return-to-run
sequence, not a training week, and a physio should see it. Say that plainly.

If they are pointing at a race, give the verdict on whether to start it and the
reasons. Do not soften it. A runner who should not start a race is better told
now than at the start line.

Be direct and short. Never diagnose or name a condition.
{HONESTY}""",
    tools=[get_journal, get_athlete_state, get_pain_questions, get_return_to_run_plan,
           get_race_verdict, get_fitness, get_run_history, remember_symptom,
           remember_pain_detail, remember_symptom_cleared, remember_advice],
)

_plan_writer = Agent(
    model=build_model(), callback_handler=None,
    system_prompt=f"""You write one week of running.

You have no data tools. Work from what the specialists told you in the brief.
If the brief does not contain something you need, say so rather than guessing.

Rules that override anything the runner asks for:
- If the physio says do not run, the week contains NO running. Write the
  return-to-run steps instead. Zero sessions is a valid and sometimes correct
  answer, and a runner asking for a big week does not change that.
- If almost none of their running is easy, most of this week is easy, and say
  the heart rate to stay under.
- One quality session a week at most for anyone in their first months.
- The long run stays under about a third of the week.
- Never exceed the ceiling you were given.

Output the week as a short list with day, what it is, and distance, then the
total. If a previous version was rejected, fix the actual problem rather than
shaving a kilometre off.
{HONESTY}""",
    tools=[],
)

_safety_officer = Agent(
    model=build_model(), callback_handler=None,
    system_prompt=f"""You decide whether a proposed week is safe. You are the
last check before anything reaches the runner.

Call check_proposed_week with the week's total. A verdict of reject means you
reject. Caution means you reject unless everything else is clean.

Also reject when:
- the journal has an open symptom, or the runner is in pain, or they have been
  off a week or more, and the plan contains running at all
- the week is mostly hard running for someone who has no easy days
- the long run is more than about a third of the week
- it repeats a pattern that already went wrong for this runner

Your answer is a verdict, not an essay. Do not re-tell their training history,
do not comment on their form, do not give coaching advice. One or two sentences
of reason with the numbers that drove it. That is all.""",
    tools=[check_proposed_week, get_athlete_state, get_journal, get_workload_ratio],
)

_publisher = Agent(
    model=build_model(), callback_handler=None,
    system_prompt="""You send approved sessions to the runner's watch.

Call publish_workout once per session, passing the approved week text exactly
as you received it. The tool checks it against what the safety check approved
and refuses if it does not match.

If a result says refused, say so plainly and stop. If a result says demo mode,
that is not a failure: say the week was set up but nothing went to a real
watch. Never invent a connection problem and never tell anyone to resync.

One line per session. Nothing else.""",
    tools=[publish_workout],
)


def clear_specialists():
    """Wipe the specialists' conversation history.

    They are long-lived objects, so without this each request inherits the last
    one's messages and they start answering a question nobody asked. Only the
    coach keeps a thread, because only the coach is talking to a person.
    """
    for a in (_load_analyst, _form_analyst, _physio, _plan_writer,
              _safety_officer, _publisher):
        a.messages = []


def _wrap(agent, name):
    def call(text):
        answer = str(agent(text))
        record(name, text, answer)
        return answer
    return call


@tool
def load_analyst(question: str) -> str:
    """Ask how much running this person has done and how hard it was.

    Covers weekly distance, whether the build-up was too fast, long run size,
    and crucially whether any of their running is actually easy. Ask this first.

    Args:
        question: what you want to know.
    """
    return _wrap(_load_analyst, "load_analyst")(question)


@tool
def form_analyst(question: str) -> str:
    """Ask how this person moves when they run: cadence, landing, durability.

    Args:
        question: what you want to know.
    """
    return _wrap(_form_analyst, "form_analyst")(question)


@tool
def physio(question: str) -> str:
    """Ask whether this person should be running at all, and whether they
    should start their race.

    ALWAYS ask this before asking for a plan. It is the only part of the system
    that knows whether anything hurts.

    Args:
        question: what you want to know about their condition or their race.
    """
    return _wrap(_physio, "physio")(question)


@tool
def plan_writer(brief: str) -> str:
    """Ask for a week of training. Pass everything the specialists found,
    including the ceiling and whether the physio said not to run. It has no
    data of its own and can only work from what you give it.

    Args:
        brief: the full picture, plus any rejection reason to fix.
    """
    return _wrap(_plan_writer, "plan_writer")(brief)


@tool
def safety_officer(proposed_week: str) -> str:
    """Submit a proposed week for the safety check. It can and does reject.

    The decision is arithmetic, not judgement. The model is used only to read
    the weekly total out of the proposal and to write the reason in plain
    words. Whether the week passes is decided by ramp_check in Python, so no
    wording in the proposal can talk it round.

    Args:
        proposed_week: the proposal, verbatim, including the weekly total.
    """
    import json as _json

    # the model reads the total out of the text. that is all it decides.
    try:
        read = _safety_officer.structured_output(ProposedWeek, proposed_week)
        km = float(read.total_km)
    except Exception:
        km = _km_from_text(proposed_week)

    # the verdict itself is code
    check = _json.loads(check_proposed_week(km))
    approved = check["verdict"] == "approve"
    state = _json.loads(get_athlete_state())

    # How bad it is decides this, not merely that something was mentioned.
    # A two out of ten that is settling does not block a week. A six that hurts
    # when you walk does.
    import athlete as _athlete
    hurt = _athlete.pain_severity(_athlete.state())

    if hurt["level"] == "stop":
        approved = False
        reason = ("This needs looking at before any running week: "
                  + ", ".join(hurt["concerns"]) + ".")
    elif hurt["level"] == "unknown" and (state.get("days_off") or 0) >= 7:
        # nobody has asked how bad it is and they have been off a while, so be
        # careful rather than absolute: allow a small week, not a normal one
        cap = min(check.get("ceiling_km", 0.0), 8.0)
        approved = km <= cap
        reason = (check["reason"] if approved else
                  f"Until someone has asked how bad the pain actually is, keep the "
                  f"first week back under about {cap:.0f} km.")
        check["ceiling_km"] = cap
    elif hurt["level"] == "careful":
        cap = round(check.get("ceiling_km", 0.0) * 0.8, 1)
        approved = approved and km <= cap
        reason = (check["reason"] if approved else
                  f"The pain is mild but real, so this week stays under {cap:.0f} km.")
        check["ceiling_km"] = cap
    else:
        reason = check["reason"]

    verdict = Verdict(approved=approved, reason=reason, proposed_week_km=km,
                      safe_ceiling_km=check.get("ceiling_km", 0.0))
    gate().record(proposed_week, verdict)
    journal.add_plan(_this_monday(), [], km, approved, verdict.safe_ceiling_km,
                     [] if approved else [reason])

    answer = (f"VERDICT: {'APPROVED' if approved else 'REJECTED'}\n"
              f"{reason}\n"
              f"Most this runner should do this week: {verdict.safe_ceiling_km} km")
    record("safety_officer", proposed_week, answer)
    return answer


@tool
def publisher(approved_week: str) -> str:
    """Send an approved week to the watch. Refuses anything the safety check
    did not approve.

    Args:
        approved_week: the approved week, exactly as the safety check saw it.
    """
    return _wrap(_publisher, "publisher")(approved_week)
