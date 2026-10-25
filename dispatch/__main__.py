"""Input path in, competition schedule out. Diagnostics never enter stdout."""
from time import perf_counter
PROCESS_STARTED = perf_counter()
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys

from tester.inputs import read_input
from tester.checker import check
from .coverage import CoverageConfig
from .optimizer import SolverConfig
from .simulation import SimulationConfig, simulate


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("--mode", choices=("online", "offline"), default="online")
    ap.add_argument("--scheduler", choices=("milp", "greedy"), default="milp")
    ap.add_argument("--time-limit", type=float, default=SolverConfig().time_limit,
                    help="seconds per incident replan (default: %(default)s)")
    ap.add_argument("--run-time-limit", type=float, default=20.0,
                    help="seconds for the whole run including startup/output reserve (default: 20)")
    ap.add_argument("--priorities", default="response,worst,travel,deployments")
    ap.add_argument("--dp-limit", type=int, default=SolverConfig().dp_limit,
                    help="maximum queue for exact subset DP; zero selects MILP only (default: 7)")
    deployment = ap.add_mutually_exclusive_group()
    deployment.add_argument("--staging", dest="staging", action="store_true",
                            help="Strategy 4 dynamic positioning (default)")
    deployment.add_argument("--no-staging", dest="staging", action="store_false",
                            help="legacy base deployment and return after idle jobs")
    ap.set_defaults(staging=True)
    ap.add_argument("--bounds", nargs=4, type=int, default=(0, 9, 0, 9), metavar=("XMIN", "XMAX", "YMIN", "YMAX"))
    ap.add_argument("--coverage-objective", choices=("center", "median"), default="center")
    ap.add_argument("--relocation-weight", type=float, default=0.1)
    ap.add_argument("--deployment-weight", type=float, default=0.05)
    ap.add_argument("--coverage-time-limit", type=float, default=CoverageConfig().time_limit,
                    help="legacy option: zero disables coverage planning; positive values do not limit grid search")
    ap.add_argument("--coverage-cooldown", type=int, default=10)
    ap.add_argument("--min-coverage-improvement", type=float, default=0.5)
    ap.add_argument("--start-time", type=int, default=0, help="absolute minutes; staging begins here")
    ap.add_argument("--report", type=Path, help="write assignments, solver diagnostics and metrics as JSON")
    args = ap.parse_args()
    if not math.isfinite(args.run_time_limit) or args.run_time_limit < 0:
        ap.error("run time limit must be finite and nonnegative")
    n, calls = read_input(args.input)
    config = SimulationConfig(args.mode, args.scheduler,
                              SolverConfig(args.time_limit, tuple(args.priorities.split(",")), dp_limit=args.dp_limit),
                              args.staging,
                              CoverageConfig(tuple(args.bounds), args.coverage_objective,
                                             args.relocation_weight, args.deployment_weight,
                                             args.min_coverage_improvement, args.coverage_cooldown,
                                             args.coverage_time_limit), args.start_time,
                              max(0.0, args.run_time_limit-(perf_counter()-PROCESS_STARTED)-1.0))
    result = simulate(n, calls, config)
    checked = check(n, calls, result.output, allow_reposition=args.staging)
    if not checked.valid:
        raise ValueError("independent output validation failed: " + "; ".join(checked.errors))
    report = {"mode": args.mode, "staging": args.staging, "run_time_limit": args.run_time_limit,
              "metrics": result.metrics(),
              "computation_seconds": perf_counter()-PROCESS_STARTED,
              "assignments": [asdict(e) for e in result.emergencies.values()],
              "optimizations": [asdict(p) for p in result.optimizations],
              "coverage": [asdict(p) for p in result.coverage],
              "map_history": result.map_history,
              "movements": [asdict(m) for m in result.movements]}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for p in result.optimizations:
        if p.fallback_reason:
            print("Planning fallback (" + p.algorithm + "): " + p.fallback_reason, file=sys.stderr)
    sys.stdout.write(result.output)


if __name__ == "__main__":
    main()
