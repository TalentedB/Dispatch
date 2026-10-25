"""Exports solver runs as JSON traces for the visualizer in viz/.

    python3 tools/export_viz.py                          # every solver x every input
    python3 tools/export_viz.py --only greedy,hungarian --inputs "inputs/brief_*.txt"

Solvers come from solvers.txt, plus the staged Strategy 4 configuration.
Dispatch supplies exact native traces; other solvers' printed schedules are
replayed into traces. Both include per-vehicle grid paths and the independent
checker's verdict and metrics. The trace format is documented in
viz/README.md ("Trace contract") and typed in viz/src/contract/trace.ts.

Updates viz/public/traces/manifest.json and selected <input>/<solver>.json files.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tester.checker import check  # noqa: E402
from tester.inputs import (
    BASE,
    Call,
    InputError,
    Point,
    manhattan,
    parse_clock,
    parse_input,
)  # noqa: E402
from tester.runner import ROOT, build_argv, load_solvers, run_solver  # noqa: E402

SCHEMA = "uvec.trace/v1"
OUT_DIR = ROOT / "viz" / "public" / "traces"
DEFAULT_INPUTS = [str(ROOT / "inputs" / "*.txt"), str(ROOT / "inputs" / "generated" / "*.txt")]

_LINE = re.compile(r"Vehicle\s+(\d+)\s*:\s*(\d{1,2}:\d{2})\s+(.+)", re.IGNORECASE)
_LEG = re.compile(r"(\d+) minutes? (north|south|east|west)")
_STEP = {"north": (0, 1), "south": (0, -1), "east": (1, 0), "west": (-1, 0)}


def _xy(p: Point) -> list[int]:
    return [p.x, p.y]


def _along(path: list[Point], elapsed: int) -> Point:
    """Where a vehicle is after driving `elapsed` minutes along a polyline of grid points."""
    for a, b in zip(path, path[1:]):
        leg = manhattan(a, b)
        if elapsed <= leg:
            sx, sy = (b.x > a.x) - (b.x < a.x), (b.y > a.y) - (b.y < a.y)
            return Point(a.x + sx * elapsed, a.y + sy * elapsed)
        elapsed -= leg
    return path[-1]


def _parse_lines(text: str) -> list[tuple[int, int, str, str]]:
    """(absolute minute, vehicle, lowercased action, original line). Handles wrapping past midnight."""
    out, days, latest = [], 0, None
    for raw in text.splitlines():
        m = _LINE.fullmatch(raw.strip())
        if not m:
            continue
        try:
            t = parse_clock(m[2]) + 1440 * days
        except ValueError:
            continue
        if latest is not None and latest - t > 12 * 60:
            days += 1
            t += 1440
        latest = t if latest is None else max(latest, t)
        out.append((t, int(m[1]), " ".join(m[3].lower().split()), raw.strip()))
    return out


def replay(num_vehicles: int, calls: list[Call], text: str) -> list[dict]:
    """Turns a printed schedule into per-vehicle segments.

    Segment kinds: to_job, on_job, to_base. Times are absolute minutes, paths are
    [x, y] grid corners in the order driven. Best effort: an invalid schedule still
    produces whatever segments can be recovered (the checker reports the errors).
    """
    lines = _parse_lines(text)
    open_calls = sorted(calls, key=lambda c: (c.time, c.index))
    vehicles = [{"id": i, "segments": []} for i in range(num_vehicles)]
    pos = [BASE] * num_vehicles
    pending: list[tuple[str, int] | None] = [None] * num_vehicles

    def upcoming_duration(i: int, vid: int) -> int | None:
        started = None
        for t, v, action, _ in lines[i + 1 :]:
            if v != vid:
                continue
            if action == "start job":
                started = t
            elif action == "finish job" and started is not None:
                return t - started
            elif action.startswith("start route"):
                return None
        return None

    def depart(i: int, vid: int, kind: str, t: int, legs: list[tuple[int, int]]) -> None:
        segs = vehicles[vid]["segments"]
        start = pos[vid]
        last = segs[-1] if segs else None
        if last and last["kind"] == "to_base" and last["end"] > t:
            # Redirected on the way home: start from wherever it got to.
            path = [Point(*p) for p in last["path"]]
            start = _along(path, t - last["start"])
            last["end"], last["interrupted"] = t, True
        path = [start]
        for dx, dy in legs:
            path.append(Point(path[-1].x + dx, path[-1].y + dy))
        end = path[-1]
        seg = {
            "kind": kind,
            "start": t,
            "end": t + manhattan(start, end),
            "path": [_xy(p) for p in path],
        }
        if kind == "to_job":
            ready = [c for c in open_calls if c.location == end and c.time <= t]
            duration = upcoming_duration(i, vid)
            if duration is not None and any(c.duration == duration for c in ready):
                ready = [c for c in ready if c.duration == duration]
            if ready:
                open_calls.remove(ready[0])
                seg["callId"] = ready[0].index
        segs.append(seg)
        pos[vid] = end

    for i, (t, vid, action, _) in enumerate(lines):
        if not 0 <= vid < num_vehicles:
            continue
        if pending[vid] and not action.startswith("drive"):
            kind, start_t = pending[vid]
            pending[vid] = None
            depart(i, vid, kind, start_t, [])  # zero-length trip, no Drive line printed
        segs = vehicles[vid]["segments"]
        if action == "start route to job":
            pending[vid] = ("to_job", t)
        elif action == "start route to base":
            pending[vid] = ("to_base", t)
        elif action.startswith("drive") and pending[vid]:
            kind, start_t = pending[vid]
            pending[vid] = None
            legs = []
            for amount, direction in _LEG.findall(action):
                sx, sy = _STEP[direction]
                legs.append((sx * int(amount), sy * int(amount)))
            depart(i, vid, kind, start_t, legs)
        elif action == "start job" and segs and segs[-1]["kind"] == "to_job":
            segs[-1]["end"] = t
            seg = {"kind": "on_job", "start": t, "end": t, "path": [segs[-1]["path"][-1]]}
            if "callId" in segs[-1]:
                seg["callId"] = segs[-1]["callId"]
            segs.append(seg)
        elif action == "finish job" and segs and segs[-1]["kind"] == "on_job":
            segs[-1]["end"] = t
        elif action == "arrive at base" and segs and segs[-1]["kind"] == "to_base":
            segs[-1]["end"] = t
            pos[vid] = BASE

    for vid, p in enumerate(pending):
        if p:
            depart(len(lines), vid, p[0], p[1], [])
    return vehicles


def build_trace(
    algorithm: str,
    scenario: str,
    input_text: str,
    output: str,
    label: str | None = None,
    group: str | None = None,
) -> dict:
    num_vehicles, calls = parse_input(input_text)
    vehicles = replay(num_vehicles, calls, output)
    result = check(num_vehicles, calls, output)
    times = [c.time for c in calls] + [s["end"] for v in vehicles for s in v["segments"]]
    log = [{"time": t, "vehicle": v, "text": line} for t, v, _, line in _parse_lines(output)]
    return {
        "schema": SCHEMA,
        "algorithm": {"id": algorithm},
        "scenario": {
            "id": scenario,
            "label": label or scenario,
            "group": group,
            "vehicles": num_vehicles,
        },
        "calls": [
            {
                "id": c.index,
                "time": c.time,
                "x": c.location.x,
                "y": c.location.y,
                "duration": c.duration,
            }
            for c in calls
        ],
        "vehicles": vehicles,
        "span": {"start": max(0, min(times, default=0) - 5), "end": max(times, default=0) + 5},
        "check": {"valid": result.valid, "errors": result.errors},
        "metrics": result.metrics.as_dict() if result.metrics else None,
        "log": log,
    }


def _group(path: Path) -> str:
    if path.parent.name == "generated":
        return "generated"
    return "brief" if path.stem.startswith("brief") else "custom"


def export_run(name: str, command: str, path: Path, timeout: float) -> dict:
    """Use dispatch's native trace; retain text replay for existing solvers.

    Dispatch movements carry exact call IDs and physically truncated staging
    paths that cannot be recovered unambiguously from the legacy text format.
    """
    if command.startswith("python3 "):
        command = f'"{sys.executable}" ' + command[len("python3 ") :]
    arguments = build_argv(command, path)
    native_dispatch = any(
        arguments[index : index + 2] == ["-m", "dispatch"] for index in range(len(arguments) - 1)
    )
    with tempfile.TemporaryDirectory(prefix="uvec-trace-") as directory:
        trace_path = Path(directory) / "trace.json"
        if native_dispatch:
            command += f' --trace "{trace_path.as_posix()}"'
        run = run_solver(command, path, timeout)
        if not run.ok:
            raise ValueError(run.stderr.strip()[-200:] or f"exit code {run.returncode}")
        trace = (
            json.loads(trace_path.read_text(encoding="utf-8"))
            if native_dispatch
            else (
                json.loads(run.stdout)
                if name == "abdullah"
                else build_trace(name, path.stem, path.read_text(), run.stdout)
            )
        )
    if not trace["check"]["valid"]:
        raise ValueError("invalid schedule: " + "; ".join(trace["check"]["errors"][:3]))
    trace["algorithm"]["id"] = name
    trace["scenario"].update(label=path.stem.replace("_", " "), group=_group(path))
    trace["metrics"]["computation_seconds"] = run.seconds
    return trace


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--inputs", nargs="*", default=DEFAULT_INPUTS, help="input files or globs")
    ap.add_argument("--only", help="comma-separated solver names from solvers.txt")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--timeout", type=float, default=20.0)
    args = ap.parse_args(argv)

    solvers = load_solvers()
    # Native traces preserve standby travel, which the legacy text format cannot express.
    solvers["abdullah"] = f'"{sys.executable}" -m tools.abdullah_trace {{input}}'
    # Staging is a visualizer capability and requires an explicit checker opt-in
    # in bench.py; keep the legacy benchmark registry on base deployment.
    solvers.setdefault("strategy4", "python -m dispatch {input}")
    if args.only:
        wanted = args.only.split(",")
        missing = [name for name in wanted if name not in solvers]
        if missing:
            ap.error("unknown solver(s): " + ", ".join(missing))
        solvers = {n: c for n, c in solvers.items() if n in wanted}
    if not solvers:
        print("no solvers to run (check solvers.txt / --only)", file=sys.stderr)
        return 1
    paths = sorted({Path(p) for pattern in args.inputs for p in glob.glob(pattern)})

    if not paths:
        print("no input files found", file=sys.stderr)
        return 1
    # Incremental exports preserve other algorithms/scenarios, so --only does
    # not remove the frontend's existing comparisons or unrelated files.
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    scenarios = {entry["id"]: entry for entry in previous.get("scenarios", [])}
    failures = 0
    for path in paths:
        text = path.read_text()
        try:
            num_vehicles, calls = parse_input(text)
        except InputError as e:
            print(f"skip {path.name}: {e}", file=sys.stderr)
            continue
        entry = {
            "id": path.stem,
            "label": path.stem.replace("_", " "),
            "group": _group(path),
            "vehicles": num_vehicles,
            "calls": len(calls),
            "traces": dict(scenarios.get(path.stem, {}).get("traces", {})),
        }
        for name, command in solvers.items():
            try:
                trace = export_run(name, command, path, args.timeout)
            except (ValueError, OSError) as error:
                failures += 1
                entry["traces"].pop(name, None)
                print(f"  {name} on {path.stem}: failed ({error})", file=sys.stderr)
                continue
            rel = f"{path.stem}/{name}.json"
            (args.out / path.stem).mkdir(parents=True, exist_ok=True)
            (args.out / rel).write_text(json.dumps(trace, separators=(",", ":")))
            entry["traces"][name] = rel
            status = (
                "ok"
                if trace["check"]["valid"]
                else f"INVALID ({len(trace['check']['errors'])} errors)"
            )
            print(f"  {path.stem:<22} {name:<18} {status}")
        scenarios[path.stem] = entry

    entries = sorted(scenarios.values(), key=lambda entry: entry["id"])
    algorithms = list(dict.fromkeys(name for entry in entries for name in entry["traces"]))
    manifest = {"schema": SCHEMA, "algorithms": algorithms, "scenarios": entries}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"manifest contains {sum(len(s['traces']) for s in entries)} traces in {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
