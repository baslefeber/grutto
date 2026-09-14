"""Grutto running on its own, without anyone asking it to.

    python schedule.py check        do whatever is due, say nothing if nothing is
    python schedule.py weekly       write this week's plan
    python schedule.py after-run    react to any run that has appeared

`check` is the one you put on a timer. Every hour is plenty:

    0 * * * *  cd /path/to/grutto && .venv/bin/python schedule.py check

It writes what it decided into the journal, so the app has something waiting
the next time it is opened. In a real product this is where a push
notification goes out. Nothing is sent here, because pretending otherwise
would be a lie.

The watcher only knows about runs the data source gives it. Today that is
Garmin. The same two moments, the start of a week and the end of a run, exist
in Strava and in Apple Health, and the source interface is the only thing that
would need a new class.
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "tools"))

from dotenv import load_dotenv

load_dotenv()

import agent_tools
import athlete
import journal
import recorder
import watcher
from garmin_source import get_source
from gate import gate


def _setup():
    known = journal.recall_pain_detail()
    runner = journal.summary()["runner"]
    open_ = journal.open_symptoms()
    athlete.set_state(
        age=runner.get("age", 27), vo2_max=51.7,
        pain=open_[0]["text"] if open_ else "",
        pain_area=open_[0].get("area", "") if open_ else "",
        days_off=0,
        goal_race=runner.get("goal_race", ""),
        goal_race_date=runner.get("goal_race_date", ""),
        **known)
    recorder.reset()
    gate().reset()
    agent_tools.reset_source()


def after_run(quiet=False):
    """Say something about any run that has turned up since last time."""
    runs = get_source().runs()
    new = watcher.unreviewed_runs(runs)
    if not new:
        if not quiet:
            print("nothing new to look at")
        return None

    latest = max(new, key=lambda r: r["date"])
    _setup()
    from specialists import clear_specialists
    clear_specialists()

    from reviewer import build_reviewer
    today = date.today().isoformat()
    runner = journal.summary()["runner"]
    race = runner.get("goal_race_date", "")
    days_to_race = ""
    if race:
        days_to_race = (f" Their {runner.get('goal_race', 'race')} is on {race}, "
                        f"which is {(date.fromisoformat(race) - date.today()).days} "
                        f"days from today.")

    said = str(build_reviewer()(
        f"Today is {today}. They have just finished a run: {latest['name']} on "
        f"{latest['date']}, {latest['distance_m'] / 1000:.1f} km in "
        f"{latest['duration_s'] / 60:.0f} minutes, average heart rate "
        f"{latest.get('avg_hr')}.{days_to_race} "
        f"Say what is worth saying about it."))

    journal.add_event("run_review", said.strip(), on=latest["date"],
                      run_date=latest["date"])
    watcher.mark_reviewed(new)
    return said


def weekly(today=None, quiet=False):
    """Write the week, on the morning the week starts."""
    due, monday = watcher.weekly_due(today)
    if not due:
        if not quiet:
            print(f"this week's plan was already written ({monday})")
        return None

    _setup()
    from specialists import clear_specialists
    clear_specialists()

    from coach import build_coach
    said = str(build_coach(session_id=f"weekly-{monday}")(
        "It is the start of a new running week. Write it."))

    journal.add_event("weekly_plan", said.strip(), on=monday)
    watcher.mark_weekly_done(monday)
    return said


def main():
    what = (sys.argv[1] if len(sys.argv) > 1 else "check").lower()
    today = sys.argv[2] if len(sys.argv) > 2 else None

    if what == "weekly":
        out = weekly(today)
    elif what == "after-run":
        out = after_run()
    elif what == "check":
        # whatever is due. silence is the correct output most of the time.
        out = after_run(quiet=True) or weekly(today, quiet=True)
        if out is None:
            return
    else:
        sys.exit(f"unknown: {what}. use check, weekly or after-run")

    if out:
        print(f"\n{out.strip()}\n")


if __name__ == "__main__":
    main()
