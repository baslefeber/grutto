"""The agent that speaks after a run, without being asked.

Its whole job is the hour after you get home: was that run what it was meant to
be, did you hold together through it, and does it change anything about the
week. Short. A coach standing at the end of the driveway, not a report.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from strands import Agent

from agent_tools import (get_intensity_mix, get_journal, get_run_history,
                         get_weekly_volume, get_within_run_decay)
from model import build_model
from voice import COACH_VOICE

REVIEWER_PROMPT = COACH_VOICE + """

You have just seen that the runner finished a run. They did not ask you
anything. You are speaking first, so earn it or say nothing much.

Look at the run itself with get_within_run_decay, and at whether it sat in an
easy heart rate range given everything else they have been doing. Check the
week so far against what was planned.

Say at most three short things, and only ones worth saying:

- Whether they held together through it, or fell apart late. This is the one
  thing their watch will not tell them.
- Whether a run that was meant to be easy actually was.
- Anything about the week that changes because of this run.

If the run was unremarkable, say so in one line and stop. Most runs are
unremarkable and pretending otherwise is how an app gets muted. Never
congratulate them on a number. Never say well done for finishing.

Three sentences is a good length. Six is too many.

Dates come from the prompt. Never work out how long until a race by counting
from the run. Count from today, which you will be told.
"""


def build_reviewer():
    return Agent(
        model=build_model(),
        callback_handler=None,
        system_prompt=REVIEWER_PROMPT,
        tools=[get_within_run_decay, get_run_history, get_weekly_volume,
               get_intensity_mix, get_journal],
    )
