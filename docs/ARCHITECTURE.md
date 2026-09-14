# How Grutto is built

```mermaid
flowchart TB
    user([Runner asks for a week]) --> coach

    subgraph orchestration [ ]
        coach["<b>coach</b><br/>runs the negotiation<br/>has no data tools of its own"]
    end

    coach -->|1. what has training looked like?| load
    coach -->|2. is their running improving?| form
    coach -->|3. write me a week| plan
    coach -->|4. is this safe?| safety
    safety -.->|REJECTED + reason| coach
    coach -.->|5. try again, here's why| plan
    coach -->|6. publish it| pub

    subgraph specialists [Five agents, each with its own memory and tools]
        load["<b>load_analyst</b><br/>weekly distance<br/>acute:chronic ratio"]
        form["<b>form_analyst</b><br/>ground contact, cadence<br/>decay inside a run"]
        plan["<b>plan_writer</b><br/>proposes the week"]
        safety["<b>safety_officer</b><br/>approves or rejects"]
        pub["<b>publisher</b><br/>sends to the watch"]
    end

    load --> tools
    form --> tools
    plan --> tools
    safety --> tools
    pub --> tools

    subgraph toolbox [Plain Python. No AI. Just sums.]
        tools["load.py  weekly volume, workload ratio, ramp check<br/>form.py  form drift, within-run decay"]
    end

    tools --> src

    subgraph data [One interface, three ways to get data]
        src["garmin_source.py"]
        src --> fix["FixtureSource<br/>recorded runs<br/>no login needed"]
        src --> con["ConnectSource<br/>unofficial library<br/>your own account"]
        src --> off["OfficialSource<br/>Garmin partner API<br/>not built yet"]
    end
```

## The part that matters

Step 4 into step 5 is the whole idea. The safety officer can say no, and when it
does, the reason goes back to the plan writer and the week gets rewritten.

That loop is not written in code. The safety officer is told it is allowed to
reject. The coach is told what to do when it does. The two of them work out the
rest between themselves.

## Why five agents instead of one

Each agent has its own memory. The load analyst reads every run and every week,
which is a lot of numbers. The coach never sees any of it, only the two
paragraphs the analyst writes at the end.

With one big agent, all those numbers would pile up in the same memory and crowd
out everything else. Splitting the work keeps each one reading only what it
needs.

## Where the thinking stops and the maths starts

Every number comes from ordinary Python in `tools/`. Weekly distance, the
acute:chronic ratio, form trends, heart rate against pace. The agents read those
numbers and explain them to you. They never work them out themselves, because
models are bad at arithmetic and good at judgement.
