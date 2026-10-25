"""Input path in, competition schedule out. Diagnostics never enter stdout."""

from time import perf_counter

# Import time is part of the whole-run deadline, including solver initialization.
PROCESS_STARTED = perf_counter()
OUTPUT_RESERVE_SECONDS = 1.0
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
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("input")
    argument_parser.add_argument("--mode", choices=("online", "offline"), default="online")
    argument_parser.add_argument("--scheduler", choices=("milp", "greedy"), default="milp")
    argument_parser.add_argument(
        "--time-limit",
        type=float,
        default=SolverConfig().time_limit,
        help="seconds per incident replan (default: %(default)s)",
    )
    argument_parser.add_argument(
        "--run-time-limit",
        type=float,
        default=20.0,
        help="seconds for the whole run including startup/output reserve (default: 20)",
    )
    argument_parser.add_argument("--priorities", default="response,worst,travel,deployments")
    argument_parser.add_argument(
        "--dp-limit",
        type=int,
        default=SolverConfig().dp_limit,
        help="maximum queue for exact subset DP; zero selects MILP only (default: 7)",
    )
    deployment = argument_parser.add_mutually_exclusive_group()
    deployment.add_argument(
        "--staging",
        dest="staging",
        action="store_true",
        help="Strategy 4 dynamic positioning (default)",
    )
    deployment.add_argument(
        "--no-staging",
        dest="staging",
        action="store_false",
        help="legacy base deployment and return after idle jobs",
    )
    argument_parser.set_defaults(staging=True)
    argument_parser.add_argument(
        "--bounds",
        nargs=4,
        type=int,
        default=(0, 9, 0, 9),
        metavar=("XMIN", "XMAX", "YMIN", "YMAX"),
    )
    argument_parser.add_argument(
        "--coverage-objective", choices=("center", "median"), default="center"
    )
    argument_parser.add_argument("--relocation-weight", type=float, default=0.1)
    argument_parser.add_argument("--deployment-weight", type=float, default=0.05)
    argument_parser.add_argument(
        "--coverage-time-limit",
        type=float,
        default=CoverageConfig().time_limit,
        help="legacy option: zero disables coverage planning; positive values do not limit grid search",
    )
    argument_parser.add_argument("--coverage-cooldown", type=int, default=10)
    argument_parser.add_argument("--min-coverage-improvement", type=float, default=0.5)
    argument_parser.add_argument(
        "--start-time", type=int, default=0, help="absolute minutes; staging begins here"
    )
    argument_parser.add_argument(
        "--report", type=Path, help="write assignments, solver diagnostics and metrics as JSON"
    )
    args = argument_parser.parse_args()
    if not math.isfinite(args.run_time_limit) or args.run_time_limit < 0:
        argument_parser.error("run time limit must be finite and nonnegative")
    fleet_size, calls = read_input(args.input)
    config = SimulationConfig(
        mode=args.mode,
        scheduler=args.scheduler,
        solver=SolverConfig(
            time_limit=args.time_limit,
            priorities=tuple(args.priorities.split(",")),
            dp_limit=args.dp_limit,
        ),
        staging=args.staging,
        coverage=CoverageConfig(
            bounds=tuple(args.bounds),
            objective=args.coverage_objective,
            relocation_weight=args.relocation_weight,
            deployment_weight=args.deployment_weight,
            min_improvement=args.min_coverage_improvement,
            cooldown=args.coverage_cooldown,
            time_limit=args.coverage_time_limit,
        ),
        start_time=args.start_time,
        runtime_limit=max(
            0.0, args.run_time_limit - (perf_counter() - PROCESS_STARTED) - OUTPUT_RESERVE_SECONDS
        ),
    )
    result = simulate(fleet_size, calls, config)
    checked = check(fleet_size, calls, result.output, allow_reposition=args.staging)
    if not checked.valid:
        raise ValueError("independent output validation failed: " + "; ".join(checked.errors))
    report = {
        "mode": args.mode,
        "staging": args.staging,
        "run_time_limit": args.run_time_limit,
        "metrics": result.metrics(),
        "computation_seconds": perf_counter() - PROCESS_STARTED,
        "assignments": [asdict(emergency) for emergency in result.emergencies.values()],
        "optimizations": [asdict(plan) for plan in result.optimizations],
        "coverage": [asdict(plan) for plan in result.coverage],
        "map_history": result.map_history,
        "movements": [asdict(movement) for movement in result.movements],
    }
    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for plan in result.optimizations:
        if plan.fallback_reason:
            print(
                "Planning fallback (" + plan.algorithm + "): " + plan.fallback_reason,
                file=sys.stderr,
            )
    sys.stdout.write(result.output)


if __name__ == "__main__":
    main()
