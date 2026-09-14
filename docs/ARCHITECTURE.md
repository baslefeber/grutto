# How Grutto is built

```mermaid
flowchart TB
    user([Runner asks, or a timer fires]) --> coach

    coach["<b>coach</b><br/>runs the order of work<br/>holds no data tools"]

    coach -->|1. is anything hurting?| physio
    coach -->|2. how much, how hard?| load
    coach -->|3. how do they move?| form
    coach -->|4. write me a week| plan
    coach -->|5. is this safe?| safety
    safety -.->|REFUSED + reason| coach
    coach -.->|6. again, here is why| plan
    coach -->|7. publish| pub

    timer([timer]) --> reviewer

    subgraph specialists [Six specialists, each with its own memory]
        physio["<b>physio</b><br/>asked first, every time<br/>can stop the week entirely"]
        load["<b>load_analyst</b><br/>weekly distance, ramp<br/>how much is actually easy"]
        form["<b>form_analyst</b><br/>cadence, landing, durability"]
        plan["<b>plan_writer</b><br/>proposes the week<br/>has no data tools"]
        safety["<b>safety_officer</b><br/>reads the numbers out<br/>of the plan, nothing more"]
        pub["<b>publisher</b><br/>refused unless the gate agrees"]
    end

    subgraph unattended [Speaks without being asked]
        reviewer["<b>reviewer</b><br/>after a run<br/>schedule.py on a timer"]
    end

    safety --> gate
    pub --> gate

    subgraph code [Plain Python. No model involved.]
        gate["<b>gate.py</b> fingerprints the approved week<br/>
              <b>load.py</b> weekly ramp AND single run jump<br/>
              <b>athlete.py</b> pain severity, intensity, race call<br/>
              <b>journal.py</b> what they told us, between sessions"]
    end

    gate --> src

    subgraph data [One interface, three ways to get data]
        src["garmin_source.py"]
        src --> fix["FixtureSource<br/>recorded runs, no login"]
        src --> con["ConnectSource<br/>unofficial, your own account"]
        src --> off["OfficialSource<br/>Garmin partner API<br/>not built"]
    end
```

## The refusal is code

The safety officer is not asked for a judgement. A model reads two numbers out
of the proposal, the weekly total and the longest single run, and that is all
it does. Python decides:

- the week against the average of the four weeks before it
- the longest run against the longest of the previous month
- a harder cap on the first week back after time off
- how bad any reported pain is

A gate then fingerprints the exact week that was approved, and the publisher
refuses anything that does not match. No wording in any prompt gets a refused
week onto a watch.

## Why the agents are separate

A planner should not grade its own plan. The safety officer never sees the plan
writer's reasoning, only the proposal and the numbers, so it cannot be talked
round. The plan writer has no data tools at all, so it cannot go and find a
number that suits it.

Each agent also keeps its own memory. The load analyst reads every run and
every week; the coach only ever sees its two-paragraph conclusion.

## Where the thinking stops

Every number comes from plain Python in `tools/`. The models read those numbers
and explain them. They never work them out, because models are poor at
arithmetic and good at judgement.
