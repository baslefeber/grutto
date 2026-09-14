"""A local page for trying Grutto and marking up each agent separately.

    python review.py     then open http://localhost:5001

Pick a date, ask a question, run it. Each agent's answer appears in its own
box. Mark each one good or bad and say why. Everything you write is appended
to feedback.jsonl with the agent name and its exact answer, so the notes can
be used to fix the right prompt later.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "agents"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, render_template_string, request

import recorder
from load import acwr_series, weekly_volume

app = Flask(__name__)
FEEDBACK = Path(__file__).resolve().parent / "feedback.jsonl"

PAGE = """<!doctype html>
<title>Grutto review</title>
<style>
 :root { --bg:#faf9f7; --ink:#1a1a1a; --dim:#6b6b6b; --line:#e2e0dc;
         --good:#2d7a4f; --bad:#b3402f; --accent:#1a1a1a; }
 * { box-sizing:border-box }
 body { margin:0; background:var(--bg); color:var(--ink);
        font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
 .wrap { max-width:860px; margin:0 auto; padding:32px 24px 80px }
 h1 { font-size:22px; margin:0 0 2px; letter-spacing:-.01em }
 .sub { color:var(--dim); font-size:13px; margin-bottom:28px }
 .panel { background:#fff; border:1px solid var(--line); border-radius:10px;
          padding:18px; margin-bottom:18px }
 label { display:block; font-size:12px; color:var(--dim); margin-bottom:5px;
         text-transform:uppercase; letter-spacing:.04em }
 input[type=text], input[type=date], textarea {
   width:100%; padding:9px 11px; border:1px solid var(--line); border-radius:7px;
   font:inherit; background:#fff; color:var(--ink) }
 textarea { resize:vertical; min-height:54px }
 .row { display:flex; gap:12px; margin-bottom:12px }
 .row > div:first-child { width:170px; flex:none }
 .row > div:last-child { flex:1 }
 button { background:var(--accent); color:#fff; border:0; border-radius:7px;
          padding:10px 18px; font:inherit; font-weight:500; cursor:pointer }
 button:disabled { opacity:.45; cursor:default }
 .chart { font:12px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;
          white-space:pre; color:var(--dim); overflow-x:auto }
 .chart b { color:var(--bad); font-weight:600 }
 .agent { background:#fff; border:1px solid var(--line); border-radius:10px;
          margin-bottom:14px; overflow:hidden }
 .agent header { padding:11px 16px; border-bottom:1px solid var(--line);
                 display:flex; align-items:center; gap:10px; background:#fcfbfa }
 .agent header h3 { margin:0; font-size:13px; font-weight:600;
                    font-family:ui-monospace,Menlo,monospace }
 .n { color:var(--dim); font-size:12px }
 .body { padding:14px 16px; white-space:pre-wrap; font-size:14px }
 .q { color:var(--dim); font-size:12.5px; padding:10px 16px;
      background:#fcfbfa; border-bottom:1px solid var(--line);
      white-space:pre-wrap; max-height:90px; overflow-y:auto }
 .rate { padding:11px 16px; border-top:1px solid var(--line); background:#fcfbfa;
         display:flex; gap:8px; align-items:flex-start }
 .rate textarea { flex:1; min-height:36px }
 .vote { border:1px solid var(--line); background:#fff; color:var(--dim);
         padding:7px 12px; border-radius:7px; cursor:pointer; font-size:15px }
 .vote.on-good { border-color:var(--good); background:var(--good); color:#fff }
 .vote.on-bad { border-color:var(--bad); background:var(--bad); color:#fff }
 .saved { color:var(--good); font-size:12px; padding:0 16px 11px }
 .final { border-color:var(--ink) }
 .final header { background:var(--ink); color:#fff }
 .spin { color:var(--dim); font-size:13px; padding:14px 0 }
</style>
<div class=wrap>
  <h1>Grutto review</h1>
  <div class=sub>Run it, then mark up whichever agent got it wrong.</div>

  <div class=panel>
    <div class=chart>{{ chart }}</div>
  </div>

  <div class=panel>
    <div class=row>
      <div>
        <label>Pretend it is</label>
        <input type=date id=asof value="2026-08-24">
      </div>
      <div>
        <label>Ask it something</label>
        <input type=text id=q value="Plan my week. I am building for a half marathon and want a big week.">
      </div>
    </div>
    <button id=go onclick=run()>Run</button>
    <span id=spin class=spin></span>
  </div>

  <div id=out></div>
</div>
<script>
let runId = null;

async function run() {
  const btn = document.getElementById('go');
  btn.disabled = true;
  document.getElementById('spin').textContent = 'thinking, this takes a minute or so';
  document.getElementById('out').innerHTML = '';
  try {
    const r = await fetch('/run', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        as_of: document.getElementById('asof').value,
        question: document.getElementById('q').value})});
    const d = await r.json();
    if (d.error) { document.getElementById('out').textContent = d.error; return; }
    runId = d.run_id;
    render(d);
  } finally {
    btn.disabled = false;
    document.getElementById('spin').textContent = '';
  }
}

function esc(s){ const e=document.createElement('div'); e.textContent=s; return e.innerHTML }

function render(d) {
  let html = '';
  d.transcript.forEach((t, i) => {
    html += `<div class=agent>
      <header><h3>${esc(t.agent)}</h3><span class=n>step ${i+1}</span></header>
      <div class=q><b>asked:</b> ${esc(t.question).slice(0,400)}</div>
      <div class=body>${esc(t.answer)}</div>
      <div class=rate>
        <button class=vote onclick="vote(this,'${esc(t.agent)}',${i},'good')">&#128077;</button>
        <button class=vote onclick="vote(this,'${esc(t.agent)}',${i},'bad')">&#128078;</button>
        <textarea placeholder="what was wrong with this one?" id=note${i}></textarea>
      </div>
      <div class=saved id=saved${i}></div>
    </div>`;
  });
  html += `<div class="agent final">
      <header><h3>coach</h3><span class=n>what you would actually read</span></header>
      <div class=body>${esc(d.final)}</div>
      <div class=rate>
        <button class=vote onclick="vote(this,'coach',999,'good')">&#128077;</button>
        <button class=vote onclick="vote(this,'coach',999,'bad')">&#128078;</button>
        <textarea placeholder="what was wrong with this one?" id=note999></textarea>
      </div>
      <div class=saved id=saved999></div>
    </div>`;
  document.getElementById('out').innerHTML = html;
}

async function vote(btn, agent, i, verdict) {
  btn.parentNode.querySelectorAll('.vote').forEach(b => b.className = 'vote');
  btn.className = 'vote on-' + verdict;
  const note = document.getElementById('note' + i).value;
  await fetch('/feedback', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({run_id: runId, agent, verdict, note, step: i})});
  document.getElementById('saved' + i).textContent = 'saved';
}
</script>
"""


def chart():
    """Weekly distance, with the risky weeks marked."""
    sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
    from garmin_source import FixtureSource

    runs = FixtureSource().runs()
    weeks = weekly_volume(runs)
    risky = {a["week_starting"] for a in acwr_series(runs) if a["flag"] == "high"}
    lines = []
    for w in weeks:
        bar = "#" * max(int(w["km"] / 1.6), 1)
        mark = "   <-- too big a jump" if w["week_starting"] in risky else ""
        lines.append(f"{w['week_starting']}  {w['km']:5.1f} km  {bar}{mark}")
    return "\n".join(lines)


@app.get("/")
def index():
    return render_template_string(PAGE, chart=chart())


@app.post("/run")
def run():
    body = request.get_json()
    as_of = (body.get("as_of") or "").strip()
    question = (body.get("question") or "").strip()

    if as_of:
        os.environ["GRUTTO_AS_OF"] = as_of
    else:
        os.environ.pop("GRUTTO_AS_OF", None)

    # the source caches, so drop it whenever the date changes
    import agent_tools
    agent_tools._source = None

    recorder.reset()
    try:
        from coach import build_coach
        final = str(build_coach()(question))
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"})

    return jsonify({
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "transcript": recorder.transcript(),
        "final": final,
    })


@app.post("/feedback")
def feedback():
    entry = request.get_json()
    entry["at"] = datetime.now().isoformat(timespec="seconds")
    with FEEDBACK.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("\n  Grutto review page: http://localhost:5001\n")
    app.run(port=5001, debug=False)
