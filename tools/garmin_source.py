"""Garmin data access, behind one interface.

Everything above this boundary is source-agnostic. Swapping from the unofficial
library to the official Garmin Connect Developer Program API later means adding
one class here and changing an environment variable, not rewriting the agents.

  FixtureSource   recorded real data, no credentials    demo, judging, CI
  ConnectSource   python-garminconnect, own login       personal use only
  OfficialSource  Health + Training API                 product (not built yet)

ConnectSource uses the unofficial library. It works, but it is against Garmin's
terms for third-party use and would mean holding other people's passwords, so it
is strictly for running against your own account.
"""

import json
import os
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "runs.json"


class FixtureSource:
    """Replays recorded data. Publishing is a no-op that records intent."""

    name = "fixture"

    def __init__(self, path=FIXTURES, as_of=None):
        self._data = json.loads(Path(path).read_text())
        self.published = []
        # as_of rewinds the clock: hide everything after this date, so the
        # agents see exactly what was knowable on that day and nothing more.
        self.as_of = as_of

    def runs(self, since=None):
        rs = self._data["runs"]
        if self.as_of:
            rs = [r for r in rs if r["date"] <= self.as_of]
        return [r for r in rs if r["date"] >= since] if since else rs

    def laps(self, run_date):
        return self._data["laps"].get(run_date, [])

    def publish_workout(self, workout):
        self.published.append(workout)
        return {
            "status": "ok",
            "mode": "demo",
            "message": "Demo mode. The workout was accepted and recorded here. "
                       "Nothing was sent to a real watch, and nothing is wrong.",
            "workout": workout,
        }


class ConnectSource:
    """Live Garmin Connect via the unofficial library. Your own account only."""

    name = "connect"

    def __init__(self):
        from garminconnect import Garmin

        email = os.environ.get("GARMIN_EMAIL")
        password = os.environ.get("GARMIN_PASSWORD")
        if not email or not password:
            raise RuntimeError(
                "Set GARMIN_EMAIL and GARMIN_PASSWORD in .env to use the live source. "
                "Run with GRUTTO_SOURCE=fixture to use recorded data instead."
            )
        self._api = Garmin(email, password)
        self._api.login()

    def runs(self, since=None):
        acts = self._api.get_activities(0, 100)
        out = []
        for a in acts:
            if a.get("activityType", {}).get("typeKey") != "running":
                continue
            date = a["startTimeLocal"][:10]
            if since and date < since:
                continue
            out.append({
                "date": date,
                "name": a.get("activityName", ""),
                "distance_m": a.get("distance", 0.0),
                "duration_s": a.get("duration", 0.0),
                "avg_hr": a.get("averageHR"),
                "activity_id": a["activityId"],
                "form": {
                    "gct_ms": a.get("avgGroundContactTime"),
                    "cadence": a.get("averageRunningCadenceInStepsPerMinute"),
                    "vertical_oscillation_cm": a.get("avgVerticalOscillation"),
                    "vertical_ratio": a.get("avgVerticalRatio"),
                    "stride_length_cm": a.get("avgStrideLength"),
                    "avg_speed_mps": a.get("averageSpeed"),
                    "avg_hr": a.get("averageHR"),
                } if a.get("avgGroundContactTime") else None,
            })
        return out

    def laps(self, run_date):
        for r in self.runs():
            if r["date"] != run_date:
                continue
            data = self._api.get_activity_splits(r["activity_id"])
            return [{
                "lap": l.get("lapIndex"),
                "dist_m": l.get("distance"),
                "speed_mps": l.get("averageSpeed"),
                "hr": l.get("averageHR"),
                "cadence": l.get("averageRunCadence"),
                "power": l.get("averagePower"),
                "type": l.get("intensityType", "ACTIVE"),
            } for l in data.get("lapDTOs", [])]
        return []

    def publish_workout(self, workout):
        # Writing workouts needs the official Training API. Never fake a write.
        return {
            "status": "unsupported",
            "reason": "Publishing requires the Garmin Training API (partner approval). "
                      "Nothing was sent.",
            "workout": workout,
        }


def get_source():
    """Pick a source from GRUTTO_SOURCE. Defaults to fixtures, which is safe."""
    kind = os.environ.get("GRUTTO_SOURCE", "fixture").lower()
    if kind == "connect":
        return ConnectSource()
    if kind == "fixture":
        return FixtureSource(as_of=os.environ.get("GRUTTO_AS_OF"))
    raise ValueError(f"Unknown GRUTTO_SOURCE: {kind!r}. Use 'fixture' or 'connect'.")
