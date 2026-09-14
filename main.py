"""Grutto: a running coach that reads what your watch records and never shows you.

    python main.py                      plan the coming week
    python main.py "question"           ask something specific
    python main.py --as-of 2026-08-24   rewind to a past date
    python main.py --pain "both feet"   tell it something hurts

Set GRUTTO_SOURCE=connect with your Garmin login in .env to run against your
own account instead of the recorded data.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "agents"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

from dotenv import load_dotenv

load_dotenv()

import agent_tools
import athlete
import recorder
from coach import build_coach
from gate import gate

DEFAULT = ("Plan my coming week of running. I have a half marathon in two weeks "
           "and I have not run for ten days.")


def main():
    args = sys.argv[1:]

    def take(flag, default=None):
        if flag in args:
            i = args.index(flag)
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return default

    as_of = take("--as-of")
    pain = take("--pain", "pain under both feet")

    if as_of:
        os.environ["GRUTTO_AS_OF"] = as_of
        agent_tools.TODAY = as_of

    athlete.set_state(
        age=27, pain=pain, pain_area="both feet",
        days_off=10 if pain else 0,
        goal_race="Half marathon", goal_race_date="2026-09-27")

    recorder.reset()
    gate().reset()
    agent_tools.reset_source()

    question = " ".join(args) or DEFAULT

    print(f"\n  grutto\n  {'-' * 64}")
    if as_of:
        print(f"  rewound to {as_of}, it can only see what was known then")
    if pain:
        print(f"  reported: {pain}")
    print(f"  {'-' * 64}\n  {question}\n  {'-' * 64}\n")

    build_coach()(question)

    print(f"\n  {'-' * 64}")
    print(f"  safety gate: {gate().summary()}")
    print()


if __name__ == "__main__":
    main()
