"""Pathfinding benchmark: same calls, fleet and map for every strategy.

    python -m tools.benchmark_pathfinding                 # every input, markdown table
    python -m tools.benchmark_pathfinding --csv out.csv   # plus a per-test breakdown

P2  Manhattan                 Abdullah's fleet algorithm, but each call goes to the vehicle
                              nearest by plain (x, y) block distance; busy time is ignored.
P3  Manhattan + Z-index       Abdullah's algorithm unchanged: distance has a third axis,
                              z = minutes until the vehicle is free (fleet/pathfinding.py).
P4  Manhattan + Z-index + MLIP  The adaptive hybrid (`python -m dispatch`, strategy4):
                              MILP/DP assignment with availability-aware coverage.

Response = minutes from a call coming in to a vehicle arriving (same as the visualizer).
Decision time = wall-clock ms spent choosing assignments, per call. Deployment work
(Abdullah's post redistribution, the hybrid's coverage solve) is excluded for all three.
P4 needs highspy (requirements.txt); without it the hybrid falls back and is not measured.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import fleet.pathfinding as fp
from tester.inputs import parse_input
from tools.abdullah_trace import build_trace

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = [str(ROOT / "inputs" / "*.txt"), str(ROOT / "inputs" / "generated" / "*.txt")]
STRATEGIES = {
    "P2": "Manhattan",
    "P3": "Manhattan + Z-index",
    "P4": "Manhattan + Z-index + MLIP",
}


def manhattan_dispatch(minute, queue, vehicles, results, events):
    """fp.dispatch with the z axis (minutes until free) dropped from the distance."""
    for call in list(queue):
        target = [call[1], call[2]]
        best = min(vehicles, key=lambda v: fp.distance(fp.end_point(v)[:2], target))
        fp.assign(minute, best, call, results, events)
        queue.remove(call)


def run_fleet(text: str, scenario: str, dispatch) -> tuple[dict, float]:
    """Run Abdullah's simulation with `dispatch` swapped in, timing only the dispatch calls."""
    spent = 0.0

    def timed(minute, queue, *rest):
        nonlocal spent
        if not queue:
            return dispatch(minute, queue, *rest)
        start = time.perf_counter()
        dispatch(minute, queue, *rest)
        spent += time.perf_counter() - start

    original = fp.dispatch
    fp.dispatch = timed
    try:
        trace = build_trace(text, scenario)
    finally:
        fp.dispatch = original
    return trace, spent


def run_hybrid(path: Path, python: str) -> tuple[dict, float]:
    with tempfile.TemporaryDirectory() as tmp:
        report, trace = Path(tmp) / "report.json", Path(tmp) / "trace.json"
        run = subprocess.run([python, "-m", "dispatch", str(path), "--report", str(report), "--trace", str(trace)],
                             cwd=ROOT, capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError(run.stderr.strip()[-300:])
        if "highspy" in run.stderr:
            raise RuntimeError("highspy is not installed; P4 would silently fall back. pip install -r requirements.txt")
        detail = json.loads(report.read_text())
        return json.loads(trace.read_text()), detail["metrics"]["solver_seconds"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", nargs="*", default=DEFAULT_INPUTS)
    ap.add_argument("--csv", type=Path, help="write per-test rows here")
    ap.add_argument("--python", default=sys.executable, help="interpreter for the hybrid (needs highspy)")
    args = ap.parse_args(argv)

    paths = sorted({Path(p) for pattern in args.inputs for p in glob.glob(pattern)})
    rows = []
    for path in paths:
        text = path.read_text()
        calls = len(parse_input(text)[1])
        runs = {
            "P2": run_fleet(text, path.stem, manhattan_dispatch),
            "P3": run_fleet(text, path.stem, fp.dispatch),
            "P4": run_hybrid(path, args.python),
        }
        for key, (trace, seconds) in runs.items():
            if not trace["check"]["valid"]:
                raise RuntimeError(f"{key} invalid on {path.stem}: {trace['check']['errors'][:2]}")
            m = trace["metrics"]
            rows.append({"test": path.stem, "strategy": key, "calls": calls, "avg_response": m["avg_response"],
                         "max_response": m["max_response"], "decision_ms": 1000 * seconds / max(1, calls)})
        print(f"{path.stem:18} " + "  ".join(
            f"{k} {r['avg_response']:6.1f}" for k, r in zip(runs, rows[-3:])), file=sys.stderr)

    if args.csv:
        with args.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    print(f"\n{len(paths)} tests, {sum(r['calls'] for r in rows if r['strategy'] == 'P2')} calls each strategy\n")
    print("| Strategy | Mean response (min) | Max response (min) | Decision time (ms) | Tests won |")
    print("|---|---|---|---|---|")
    best = {t: min(r["avg_response"] for r in rows if r["test"] == t) for t in {r["test"] for r in rows}}
    for key, label in STRATEGIES.items():
        mine = [r for r in rows if r["strategy"] == key]
        total_calls = sum(r["calls"] for r in mine)
        mean = sum(r["avg_response"] * r["calls"] for r in mine) / total_calls  # weighted by calls
        worst = max(r["max_response"] for r in mine)
        decision = sum(r["decision_ms"] * r["calls"] for r in mine) / total_calls
        wins = sum(1 for r in mine if r["avg_response"] <= best[r["test"]] + 1e-9)
        print(f"| {key} {label} | {mean:.1f} | {worst} | {decision:.3f} | {wins}/{len(mine)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
