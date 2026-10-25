"""Adapt Abdullah's fleet events to the visualizer's native trace contract.

The fleet sources are preserved from origin/abdullah (25b46f2). Its active
policy is greedy dispatch plus standby posts; MILP batching is disabled there.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import sys

from fleet.pathfinding import solve
from tester.inputs import Point, manhattan, parse_input
from tools.export_viz import SCHEMA, _along


def point(text: str) -> list[int]:
    xy = [0, 0]
    for amount, direction in re.findall(r"(\d+)([NSEW])", text):
        axis = 0 if direction in "EW" else 1
        xy[axis] += int(amount) * (1 if direction in "NE" else -1)
    return xy


def build_trace(input_text: str, scenario: str, label=None, group=None) -> dict:
    count, calls = parse_input(input_text)
    incoming = [(c.time, c.location.x, c.location.y, c.duration)
                for c in sorted(calls, key=lambda c: (c.time, c.index))]
    with contextlib.redirect_stdout(io.StringIO()):
        events = solve(count, incoming)
    # Fleet IDs start at 1; the UI and the other algorithms start at 0.
    events = [(t, v - 1, text) for t, v, text in events]
    vehicles = [{"id": v, "segments": []} for v in range(count)]
    remaining = list(calls)
    errors = []
    responses, delays, used = [], [], set()
    horizon = max([c.time for c in calls] + [t for t, _, _ in events], default=0)

    for vid, vehicle in enumerate(vehicles):
        pos = [0, 0]
        segments = vehicle["segments"]
        own = [e for e in events if e[1] == vid]
        for index, (t, _, text) in enumerate(own):
            if text.startswith("Start Route to "):
                if segments and segments[-1]["end"] > t:
                    previous = segments[-1]
                    if previous["kind"] != "reposition":
                        errors.append(f"vehicle {vid}: interrupted committed job at {t}")
                    actual = _along([Point(*p) for p in previous["path"]], t - previous["start"])
                    pos = [actual.x, actual.y]
                    previous.update(end=t, interrupted=True)
                elif segments:
                    pos = segments[-1]["path"][-1]
                target = point(text)
                distance = sum(abs(a - b) for a, b in zip(pos, target))
                path = [pos[:]]
                if pos[0] != target[0]:
                    path.append([target[0], pos[1]])
                if path[-1] != target:
                    path.append(target)
                segments.append({"kind": "to_job" if "to Job " in text else "reposition",
                                 "start": t, "end": t + distance, "path": path})
            elif text.startswith("Arrive at Job "):
                target = point(text)
                # Arrival is followed by Start/Finish Job. Duration disambiguates
                # simultaneous calls with identical coordinates.
                finish = next((e[0] for e in own[index + 1:] if e[2] == "Finish Job"), None)
                if finish is None:
                    errors.append(f"vehicle {vid}: unfinished job at {t}")
                    continue
                candidates = [c for c in remaining if c.time <= t and [c.location.x, c.location.y] == target
                              and c.duration == finish - t]
                if not candidates:
                    errors.append(f"vehicle {vid}: unmatched arrival at {t}")
                    continue
                active = min(candidates, key=lambda c: (c.time, c.index))
                remaining.remove(active)
                if segments and segments[-1]["kind"] == "to_job" and segments[-1]["end"] == t:
                    segments[-1]["callId"] = active.index
                else:
                    if segments and segments[-1]["end"] > t:
                        previous = segments[-1]
                        actual = _along([Point(*p) for p in previous["path"]], t - previous["start"])
                        pos = [actual.x, actual.y]
                        previous.update(end=t, interrupted=True)
                    elif segments:
                        pos = segments[-1]["path"][-1]
                    if pos != target:
                        errors.append(f"vehicle {vid}: arrival teleports at {t}")
                    segments.append({"kind": "to_job", "start": t, "end": t,
                                     "path": [target], "callId": active.index})
                pos = target
                segments.append({"kind": "on_job", "start": t, "end": t + active.duration,
                                 "path": [target], "callId": active.index})
                responses.append(t - active.time)
                delays.append(t - active.time - manhattan(Point(0, 0), active.location))
                used.add(vid)

        if segments and segments[-1]["kind"] == "reposition" and segments[-1]["end"] > horizon:
            segments[-1].update(end=horizon, interrupted=True)

    # Validate physical continuity independently of the fleet's diagnostics.
    served = []
    travel = 0
    for vehicle in vehicles:
        pos, end = Point(0, 0), 0
        for s in vehicle["segments"]:
            path = [Point(*p) for p in s["path"]]
            if s["start"] < end or path[0] != pos:
                errors.append(f"vehicle {vehicle['id']}: overlapping or discontinuous segment")
            length = sum(manhattan(a, b) for a, b in zip(path, path[1:]))
            if s["kind"] != "on_job":
                elapsed = s["end"] - s["start"]
                if elapsed > length or (not s.get("interrupted") and elapsed != length):
                    errors.append(f"vehicle {vehicle['id']}: invalid travel time")
                travel += elapsed
                pos = _along(path, elapsed)
                if s["kind"] == "to_job" and "callId" in s:
                    call = calls[s["callId"]]
                    if s["start"] < call.time:
                        errors.append(f"call {call.index}: dispatched before release")
            else:
                served.append(s["callId"])
                pos = path[-1]
            end = s["end"]
    if sorted(served) != sorted(c.index for c in calls):
        errors.append("not every call was served exactly once")
    times = [c.time for c in calls] + [s["end"] for v in vehicles for s in v["segments"]]
    return {
        "schema": SCHEMA,
        "algorithm": {"id": "abdullah", "label": "Abdullah · adaptive posts",
                      "description": "Greedy earliest arrival with queued jobs and adaptive standby posts. MILP batching is disabled in the source branch."},
        "scenario": {"id": scenario, "label": label or scenario, "group": group, "vehicles": count},
        "calls": [{"id": c.index, "time": c.time, "x": c.location.x, "y": c.location.y,
                   "duration": c.duration} for c in calls],
        "vehicles": vehicles,
        "span": {"start": max(0, min(times, default=0) - 5), "end": max(times, default=0) + 5},
        "check": {"valid": not errors, "errors": errors},
        "metrics": {"calls_served": len(served), "avg_response": sum(responses) / len(responses) if responses else 0,
                    "max_response": max(responses, default=0), "avg_delay": sum(delays) / len(delays) if delays else 0,
                    "total_drive": travel, "vehicles_used": len(used)},
        "log": [{"time": t, "vehicle": v, "text": f"Vehicle {v}: {t // 60:02d}:{t % 60:02d} {text}"}
                for t, v, text in sorted(events, key=lambda e: e[0])],
    }


if __name__ == "__main__":
    from pathlib import Path

    path = Path(sys.argv[1])
    print(json.dumps(build_trace(path.read_text(), path.stem)))
