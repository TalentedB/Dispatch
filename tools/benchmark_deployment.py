"""Deployment benchmark: same calls, fleet, map and pathfinding (P4, MILP) for every strategy.

    python -m tools.benchmark_deployment                 # every input, markdown table
    python -m tools.benchmark_deployment --csv out.csv   # plus a per-test breakdown

D1  Origin + static rest     Start at base; return to base after every job (`--no-staging`).
D2  Dynamic + static rest    Spread out over the map once at the start; after that a vehicle
                             rests wherever its last job finished (no repositioning).
D3  Dynamic + dynamic rest   Strategy 4: availability-aware coverage, rebalanced whenever
                             the free fleet changes (`python -m dispatch`, the default).

Response = minutes from a call coming in to a vehicle arriving (same as the visualizer).
Needs highspy (requirements.txt); without it the MILP falls back and the run is rejected.
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from pathlib import Path

import dispatch.simulation as sim
from dispatch.simulation import SimulationConfig, simulate
from dispatch.trace import build_trace
from tester.checker import check
from tester.inputs import read_input

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUTS = [str(ROOT / "inputs" / "*.txt"), str(ROOT / "inputs" / "generated" / "*.txt")]
STRATEGIES = {
    "D1": "Origin + static rest",
    "D2": "Dynamic + static rest",
    "D3": "Dynamic + dynamic rest",
}

_rebalance = sim._Simulation.rebalance_idle_vehicles


def _initial_only(self) -> None:
    """Spread the fleet before the first call is reported, then never reposition again."""
    if not self.emergencies:
        _rebalance(self)


def run(path: Path, key: str) -> dict:
    fleet, calls = read_input(str(path))
    staging = key != "D1"
    sim._Simulation.rebalance_idle_vehicles = _initial_only if key == "D2" else _rebalance
    try:
        result = simulate(fleet, calls, SimulationConfig(staging=staging))
    finally:
        sim._Simulation.rebalance_idle_vehicles = _rebalance
    fallbacks = [p.fallback_reason for p in result.optimizations if p.fallback_reason]
    if any("highspy" in f for f in fallbacks):
        raise RuntimeError("highspy is not installed; the MILP would silently fall back. pip install -r requirements.txt")
    checked = check(fleet, calls, result.output, allow_reposition=staging)
    if not checked.valid:
        raise RuntimeError(f"{key} invalid on {path.stem}: {checked.errors[:2]}")
    m = build_trace(result, path.stem, key)["metrics"]
    return {"test": path.stem, "strategy": key, "calls": len(calls),
            "avg_response": m["avg_response"], "max_response": m["max_response"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", nargs="*", default=DEFAULT_INPUTS)
    ap.add_argument("--csv", type=Path, help="write per-test rows here")
    args = ap.parse_args(argv)

    paths = sorted({Path(p) for pattern in args.inputs for p in glob.glob(pattern)})
    rows = []
    for path in paths:
        mine = [run(path, key) for key in STRATEGIES]
        rows += mine
        print(f"{path.stem:18} " + "  ".join(f"{r['strategy']} {r['avg_response']:6.1f}" for r in mine), file=sys.stderr)

    if args.csv:
        with args.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    best = {t: min(r["avg_response"] for r in rows if r["test"] == t) for t in {r["test"] for r in rows}}
    print(f"\n{len(paths)} tests\n")
    print("| Strategy | Mean response (min) | Max response (min) | Tests won |")
    print("|---|---|---|---|")
    for key, label in STRATEGIES.items():
        mine = [r for r in rows if r["strategy"] == key]
        n = sum(r["calls"] for r in mine)
        mean = sum(r["avg_response"] * r["calls"] for r in mine) / n  # weighted by calls
        worst = max(r["max_response"] for r in mine)
        wins = sum(1 for r in mine if r["avg_response"] <= best[r["test"]] + 1e-9)
        print(f"| {key} {label} | {mean:.1f} | {worst} | {wins}/{len(mine)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
