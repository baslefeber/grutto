# Grutto

A running coach that is allowed to say no.

Built with the [Strands Agents SDK](https://strandsagents.com) on Amazon Bedrock.

Named after the black-tailed godwit, the Dutch national bird. Its close
relative flies 13,000 km without landing, eating or sleeping. Going a very long
way without breaking down is the whole idea.

## The problem, in one runner's data

This is a real Garmin record. Mine. It shows what my watch told me during the
weeks that ended with me unable to run.

    27 Aug   load ratio 1.2   OPTIMAL   PRODUCTIVE
    30 Aug   load ratio 1.3   OPTIMAL   PRODUCTIVE
    04 Sep   load ratio 0.9   OPTIMAL   PRODUCTIVE

Nine days after that last reading I stopped with pain under both feet and did
not run for ten days.

Garmin does work out an acute to chronic load ratio. It is not a missing
feature. The problem is what goes into it: heart rate. I run everything at
roughly the same effort, so my load looked steady while my distance doubled.

Bone, tendon and fascia do not care how hard your heart is working. They care
how many times your foot hits the ground.

Ratio the distance instead and the same weeks look different:

    06 Jul    18.5 km
    13 Jul    10.5 km
    20 Jul    23.3 km    1.73  past the line
    27 Jul    15.9 km
    03 Aug     3.9 km
    10 Aug    29.5 km    1.63  past the line
    17 Aug     9.7 km
    24 Aug    32.0 km    1.70  past the line
    31 Aug     9.1 km
    07 Sep     0.0 km    stopped, both feet

Three weeks over. The watch flagged none of them.

There is a second thing it missed. One of those 21 runs was easy. Seventeen
were moderate and three were hard. Which means no recovery days, because there
were no easy days. Garmin has been saying this every week in its own words,
AEROBIC LOW SHORTAGE, on a screen nobody opens, with nothing attached to it.

To be clear about what is being claimed: these things happened in this order.
That is not proof one caused the other. Grutto says a week was risky. It never
says a week caused an injury.

## Why another dashboard would not have helped

Knowing was never the problem. I did less than my watch suggested and still got
hurt. What was missing was something willing to refuse.

Grutto will not write a week you have not earned. When something hurts it
writes no week at all, and says so in the first sentence.

## How it works

Six agents, each with its own memory and a small set of tools.

    coach (runs the order of work, holds no data tools)
    ├── physio          asked first, every time. is anything hurting, and
    │                   should you start that race
    ├── load_analyst    how much you ran, how fast it went up, and how much
    │                   of it was actually easy
    ├── form_analyst    cadence, how you land, whether you hold together
    ├── plan_writer     writes the week. has no data of its own
    ├── safety_officer  approves or refuses, and can refuse
    └── publisher       sends it to the watch

The plan writer proposes. The safety officer can refuse and say why. That
reason goes back and the week gets rewritten. Up to three tries, and if none
pass, the runner is told honestly that no safe week could be written.

**The refusal is enforced in code, not by asking nicely.** The safety officer
returns a typed verdict. A gate fingerprints the exact week that was approved.
The publisher refuses anything that does not match. No wording in any prompt
can push a rejected week onto a watch.

The plan writer deliberately has no data tools. It works only from what the
specialists report, so it cannot go and find a number that suits it. And the
safety officer never sees the plan writer's reasoning, only the proposal and
the numbers, so it cannot be argued into approving something.

Every calculation is plain Python in `tools/`. The models read the numbers and
explain them. They never work them out, because models are poor at arithmetic
and good at judgement.

## What it says when you are hurt

Asked for a big week, by an injured runner, two weeks out from a race:

> There's no training week to write here. The physio was clear: pain under both
> feet, 10 days off running, and a race in two weeks. That combination means no
> big week, and it means the half marathon is not safe to start.
>
> Before I say anything else, see a physiotherapist. Not after the race, now.
>
> Your longest run to date is just under 16 km, and the race is 21 km. That gap
> has never been bridged in training, and this is not the week to try.

Zero sessions. The gate was never even asked, because no week was proposed.

## Running it

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env
    python main.py

Recorded real data by default. No Garmin account needed.

    python main.py "Should I race in two weeks?"
    python main.py --as-of 2026-08-24 "Plan my week, I want a big one"
    python main.py --pain "" "Plan my week"          # as if nothing hurt

`--as-of` rewinds. The agents see only what was knowable on that date, which is
how you check what it would have said on the Monday before the injury.

There is also a web interface:

    python serve.py       # http://localhost:5001

### Your own Garmin

Put your login in `.env` and set `GRUTTO_SOURCE=connect`.

### Which Claude

Amazon Bedrock by default. Set `GRUTTO_MODEL_PROVIDER=anthropic` with an
`ANTHROPIC_API_KEY` to use the Anthropic API instead.

## Getting the data honestly

Every Garmin call goes through one interface in `tools/garmin_source.py`:

| Source | How | Good for |
|---|---|---|
| `FixtureSource` | recorded file | the demo, judging, tests |
| `ConnectSource` | unofficial `garminconnect` | your own account only |
| `OfficialSource` | Garmin's Health and Training API | a real product, not built |

The unofficial library signs in as you through Garmin's website. Fine for your
own data, not fine for anyone else's: it breaks Garmin's terms, it stops
working when Garmin changes their site, and it would mean holding other
people's passwords.

The proper route is the Garmin Connect Developer Program, where the runner
approves access on Garmin's own screen and their password never reaches us.
Garmin approves companies only. The interface exists so switching to it is one
new class rather than a rewrite.

`ConnectSource.publish_workout` refuses instead of pretending. Sending a
workout to someone's watch needs Garmin's Training API, and faking that would
be a lie in the one place it matters.

## Where it is weak

Worth saying plainly, because a coach reading this will spot it anyway.

The acute to chronic ratio comes from team sport research measured in session
effort, not running distance. The evidence in running is thinner than its
popularity suggests. It is used here as one input among several, never alone,
and the chronic window excludes the current week so a spike is not hidden
inside its own average.

Form data exists for 5 of 21 runs and kilometre splits for 1, so the form agent
is deliberately sceptical and will say the sample is too small rather than
call a trend.

One runner's history is one runner's history.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Licence

MIT.
