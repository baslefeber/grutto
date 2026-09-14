"""Form analysis for running activities.

Deterministic calculations only. No model calls here.
The agent interprets these numbers; it does not compute them.

Two signals, each built on the data Garmin actually exposes:

  within_run_decay   per-lap cadence trend and heart-rate/pace decoupling.
                     Per-lap data carries cadence, HR, pace and power but NOT
                     ground contact time, so decay is measured on what is there.

  weekly_form_drift  ground contact time, vertical ratio and cadence compared
                     across runs at a matched pace. These come from the
                     whole-run summary, which is where Garmin puts them.
"""

from statistics import mean


def _slope(xs, ys):
    """Least-squares slope. Returns 0.0 for degenerate input."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = mean(xs), mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def within_run_decay(laps, min_laps=6):
    """Measure how much form degraded over the course of one run.

    Args:
        laps: list of dicts with speed_mps, hr, cadence, type.
        min_laps: below this, the run is too short to read a trend.

    Returns a dict with:
        cadence_slope_per_km  negative means cadence fell as the run went on
        decoupling_pct        how much speed-per-heartbeat worsened, first
                              half vs second half. Above ~5% is meaningful
                              aerobic decoupling by conventional reading.
        verdict               one of: clean, mild, marked, insufficient_data
    """
    active = [l for l in laps if l.get("type") == "ACTIVE" and l.get("hr")]
    if len(active) < min_laps:
        return {"verdict": "insufficient_data", "active_laps": len(active)}

    idx = list(range(len(active)))
    cadence_slope = _slope(idx, [l["cadence"] for l in active])

    half = len(active) // 2
    first, second = active[:half], active[half:]

    # speed per heartbeat: higher is better
    eff1 = mean(l["speed_mps"] / l["hr"] for l in first)
    eff2 = mean(l["speed_mps"] / l["hr"] for l in second)
    decoupling = (eff1 - eff2) / eff1 * 100

    if decoupling >= 5.0 or cadence_slope <= -0.5:
        verdict = "marked"
    elif decoupling >= 2.5 or cadence_slope <= -0.2:
        verdict = "mild"
    else:
        verdict = "clean"

    return {
        "verdict": verdict,
        "active_laps": len(active),
        "cadence_slope_per_km": round(cadence_slope, 3),
        "cadence_first": round(mean(l["cadence"] for l in first), 1),
        "cadence_last": round(mean(l["cadence"] for l in second), 1),
        "decoupling_pct": round(decoupling, 2),
        "hr_first": round(mean(l["hr"] for l in first), 1),
        "hr_last": round(mean(l["hr"] for l in second), 1),
    }


def weekly_form_drift(runs, pace_tolerance_mps=0.12):
    """Compare form metrics across runs held at a comparable pace.

    Ground contact time naturally shortens as pace rises, so comparing runs at
    different speeds says nothing. Only runs within pace_tolerance_mps of the
    group median are compared.

    Returns a dict with the matched runs, the change from oldest to newest,
    and a verdict.
    """
    withform = [r for r in runs if r.get("form")]
    if len(withform) < 2:
        return {"verdict": "insufficient_data", "runs_with_form": len(withform)}

    speeds = sorted(r["form"]["avg_speed_mps"] for r in withform)
    median = speeds[len(speeds) // 2]
    matched = [
        r for r in withform
        if abs(r["form"]["avg_speed_mps"] - median) <= pace_tolerance_mps
    ]
    matched.sort(key=lambda r: r["date"])

    if len(matched) < 2:
        return {"verdict": "insufficient_data", "matched_runs": len(matched)}

    first, last = matched[0]["form"], matched[-1]["form"]
    gct_change = (last["gct_ms"] - first["gct_ms"]) / first["gct_ms"] * 100
    vr_change = (last["vertical_ratio"] - first["vertical_ratio"]) / first["vertical_ratio"] * 100
    cad_change = last["cadence"] - first["cadence"]

    # rising ground contact and rising vertical ratio both mean worse form
    if gct_change >= 3.0 or vr_change >= 3.0:
        verdict = "deteriorating"
    elif gct_change <= -2.0 and vr_change <= -2.0:
        verdict = "improving"
    else:
        verdict = "stable"

    return {
        "verdict": verdict,
        "matched_runs": len(matched),
        "pace_band_mps": [round(median - pace_tolerance_mps, 3),
                          round(median + pace_tolerance_mps, 3)],
        "from_date": matched[0]["date"],
        "to_date": matched[-1]["date"],
        "gct_ms": [first["gct_ms"], last["gct_ms"]],
        "gct_change_pct": round(gct_change, 2),
        "vertical_ratio": [first["vertical_ratio"], last["vertical_ratio"]],
        "vertical_ratio_change_pct": round(vr_change, 2),
        "cadence": [first["cadence"], last["cadence"]],
        "cadence_change_spm": round(cad_change, 2),
    }
