"""The web interface.

    python serve.py     then open http://localhost:5001

Serves the app in app/ and the JSON it reads. Running a plan takes a minute or
two, because six agents each think in turn.
"""

import json
import os
import sys
import threading
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "tools"))

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, request, send_from_directory

import agent_tools
import athlete
import journal
import recorder
from gate import gate
from garmin_source import get_source
from load import (acwr_series, chronic_km, days_since_last_run, long_run_share,
                  longest_run_jumps, ramp_check, weekly_volume)

app = Flask(__name__, static_folder=None)

# One runner, one set of module globals. Two requests at once used to wipe each
# other's transcript and approval, and the coach would then say a week was on
# the watch when nothing had been sent. Serialise instead.
_lock = threading.Lock()
FEEDBACK = ROOT / "feedback.jsonl"
APP_DIR = ROOT / "app"

TODAY = "2026-09-14"

# Read from this account's Garmin on 2026-09-14. Garmin's own load ratio,
# which it computes from heart rate, through the weeks before the injury.
GARMIN_SAID = [
    {"date": "2026-07-22", "week": "2026-07-20", "load_ratio": 1.1,
     "status": "OPTIMAL", "feedback": "MAINTAINING"},
    {"date": "2026-08-13", "week": "2026-08-10", "load_ratio": 1.4,
     "status": "OPTIMAL", "feedback": "PRODUCTIVE"},
    {"date": "2026-08-27", "week": "2026-08-24", "load_ratio": 1.2,
     "status": "OPTIMAL", "feedback": "PRODUCTIVE"},
    {"date": "2026-08-30", "week": "2026-08-24", "load_ratio": 1.3,
     "status": "OPTIMAL", "feedback": "PRODUCTIVE"},
    {"date": "2026-09-04", "week": "2026-08-31", "load_ratio": 0.9,
     "status": "OPTIMAL", "feedback": "PRODUCTIVE"},
]

DEFAULT_STATE = dict(
    age=27, vo2_max=51.7, pain="pain under both feet", pain_area="both feet", days_off=10,
    goal_race="Half marathon", goal_race_date="2026-09-27")


def _state_payload():
    athlete.set_state(**DEFAULT_STATE)
    src = get_source()
    runs = src.runs()

    weeks = weekly_volume(runs, TODAY)
    ratios = {a["week_starting"]: a for a in acwr_series(runs, TODAY)}
    week_rows = []
    for w in weeks:
        a = ratios.get(w["week_starting"])
        week_rows.append({
            "week_starting": w["week_starting"],
            "km": w["km"],
            "ratio": a["ratio"] if a else None,
            "flag": a["flag"] if a else None,
        })

    st = athlete.state()
    chronic = chronic_km(runs, TODAY)
    check = ramp_check(runs, 1.0, TODAY)

    from form import weekly_form_drift
    drift = weekly_form_drift(runs)
    cadence = [{"date": r["date"], "value": r["form"]["cadence"]}
               for r in runs if r.get("form")]

    return {
        "today": TODAY,
        "runner": {
            "name": "Bas",
            "days_since_last_run": days_since_last_run(runs, TODAY),
            "in_pain": st.in_pain,
            "pain_area": st.pain_area,
            "goal_race": st.goal_race,
            "goal_race_date": st.goal_race_date,
            "weeks_to_race": 2,
        },
        "weeks": week_rows,
        "chronic_km": chronic,
        "ceiling_km": check["ceiling_km"],
        "intensity": athlete.intensity_mix(runs, max_hr=st.max_hr, age=st.age),
        "form": {
            "cadence": cadence,
            "verdict": drift.get("verdict"),
            "cadence_change": drift.get("cadence_change_spm"),
        },
        "race": athlete.race_readiness(runs, 21.1, 2, st.in_pain, st.days_off or 0),
        "longest_jumps": longest_run_jumps(runs),
        "long_run_share": [s for s in long_run_share(runs) if s["too_big"]],
        "vo2_max": 51.7,
        "garmin": GARMIN_SAID,
        "runs": [{k: r.get(k) for k in
                  ("date", "name", "distance_m", "duration_s", "avg_hr", "max_hr")}
                 for r in runs],
    }


@app.get("/api/state")
def api_state():
    with _lock:
        return jsonify(_state_payload())


@app.post("/api/plan")
def api_plan():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "expected a JSON object"}), 400
    as_of = str(body.get("as_of") or "").strip()
    pain = str(body.get("pain", DEFAULT_STATE["pain"]))
    question = str(body.get("question") or "").strip() or "Plan my coming week."
    session_id = str(body.get("session_id") or "").strip() or None

    if not isinstance(body, dict):
        return jsonify({"error": "expected a JSON object"}), 400

    if as_of:
        # a bad date used to sail through and quietly return every run, which
        # is worse than failing, because the answer looks right
        try:
            date.fromisoformat(as_of)
        except ValueError:
            return jsonify({"error": f"as_of must look like 2026-08-24, got {as_of!r}"}), 400
        os.environ["GRUTTO_AS_OF"] = as_of
        agent_tools.TODAY = as_of
    else:
        os.environ.pop("GRUTTO_AS_OF", None)
        agent_tools.TODAY = TODAY

    from specialists import clear_specialists

    with _lock:
        # Anything the runner already told the physio about how bad it is
        # lives in the journal. Without this, every request resets them to
        # "in pain, severity unknown" and the same questions get asked again.
        known = journal.recall_pain_detail()
        athlete.set_state(**{**DEFAULT_STATE, "pain": pain,
                             "days_off": DEFAULT_STATE["days_off"] if pain else 0,
                             **known})
        recorder.reset()
        gate().reset()
        agent_tools.reset_source()
        clear_specialists()

        try:
            from coach import build_coach
            final = str(build_coach(session_id)(question))
        except Exception as e:
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
        finally:
            # a rewind must not survive the request that asked for it
            os.environ.pop("GRUTTO_AS_OF", None)
            agent_tools.TODAY = TODAY
            agent_tools.reset_source()

        return jsonify({
            "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
            "transcript": recorder.transcript(),
            "final": final,
            "gate": gate().summary(),
            "session_id": session_id,
        })


@app.post("/api/feedback")
def api_feedback():
    entry = request.get_json(silent=True)
    if not isinstance(entry, dict):
        return jsonify({"error": "expected a JSON object"}), 400
    entry = {k: str(v)[:2000] for k, v in entry.items()}
    entry["at"] = datetime.now().isoformat(timespec="seconds")
    with FEEDBACK.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return jsonify({"ok": True})


@app.get("/")
def index():
    return send_from_directory(APP_DIR, "index.html")


@app.get("/<path:p>")
def static_file(p):
    return send_from_directory(APP_DIR, p)


if __name__ == "__main__":
    print("\n  Grutto: http://localhost:5001\n")
    app.run(port=5001, debug=False, threaded=True)
