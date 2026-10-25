"""Run every solver on every test input and compare them.

Solvers are listed in solvers.txt (or passed with --solver). Each one is any
program that takes an input file path and prints a schedule to stdout.

    python3 bench.py                                    # all solvers, all inputs
    python3 bench.py --detail                           # also a table per input
    python3 bench.py --solver "mine=python3 my_solver.py {input}"
    python3 bench.py --only greedy,chaining --inputs "inputs/generated/rush*.txt"
    python3 bench.py --sort total_drive

Every output is replayed by tester/checker.py; rule violations make it
INVALID. Inputs with a .expected file are also compared line for line.
Raw outputs are saved to .bench_out/<solver>/<input>.out for inspection.
"""

from __future__ import annotations

import argparse
import glob
import sys
from dataclasses import dataclass
from pathlib import Path

from tester.checker import CheckResult, check
from tester.inputs import InputError, read_input
from tester.runner import ROOT, load_solvers, matches_expected, run_solver

DEFAULT_INPUTS = [str(ROOT / "inputs" / "*.txt"), str(ROOT / "inputs" / "generated" / "*.txt")]
OUT_DIR = ROOT / ".bench_out"
SORT_KEYS = ["avg_response", "max_response", "avg_delay", "total_drive", "vehicles_used"]


@dataclass
class Result:
    solver: str
    input: str
    status: str  # ok | INVALID | CRASH | TIMEOUT
    check: CheckResult | None
    matches_expected: bool | None
    seconds: float
    detail: str  # first error / stderr line, for the failure list


def run_one(name: str, command: str, path: Path, timeout: float) -> Result:
    num_vehicles, calls = read_input(str(path))
    run = run_solver(command, path, timeout)

    out_file = OUT_DIR / name / f"{path.stem}.out"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(run.stdout)

    if run.returncode is None:
        return Result(name, path.stem, "TIMEOUT", None, None, run.seconds, run.stderr)
    if not run.ok:
        last = (run.stderr.strip().splitlines() or [f"exit code {run.returncode}"])[-1]
        return Result(name, path.stem, "CRASH", None, None, run.seconds, last)

    result = check(num_vehicles, calls, run.stdout)
    return Result(name, path.stem, "ok" if result.valid else "INVALID", result,
                  matches_expected(run.stdout, path), run.seconds,
                  result.errors[0] if result.errors else "")


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(row, widths)))


def summarize(results: list[Result], solvers: list[str], sort_key: str) -> None:
    valid = [r for r in results if r.status == "ok"]
    best: dict[str, float] = {}
    for r in valid:
        best[r.input] = min(best.get(r.input, float("inf")), r.check.metrics.avg_response)

    rows = []
    for name in solvers:
        mine = [r for r in results if r.solver == name]
        ok = [r for r in mine if r.status == "ok"]
        with_expected = [r for r in mine if r.matches_expected is not None]
        calls = sum(r.check.metrics.calls_served for r in ok) or 1
        stats = {
            "avg_response": sum(r.check.metrics.avg_response * r.check.metrics.calls_served for r in ok) / calls,
            "max_response": max((r.check.metrics.max_response for r in ok), default=0),
            "avg_delay": sum(r.check.metrics.avg_delay * r.check.metrics.calls_served for r in ok) / calls,
            "total_drive": sum(r.check.metrics.total_drive for r in ok),
            "vehicles_used": sum(r.check.metrics.vehicles_used for r in ok),
        }
        rows.append((len(ok) < len(mine), stats[sort_key], [
            name,
            f"{len(ok)}/{len(mine)}",
            f"{sum(r.matches_expected for r in with_expected)}/{len(with_expected)}" if with_expected else "-",
            f"{stats['avg_response']:.2f}",
            str(stats["max_response"]),
            f"{stats['avg_delay']:.2f}",
            str(stats["total_drive"]),
            str(stats["vehicles_used"]),
            str(sum(1 for r in ok if r.check.metrics.avg_response == best[r.input])),
            f"{sum(r.seconds for r in mine):.2f}",
        ]))

    # Solvers with any failed run sink to the bottom; metrics only count valid runs.
    rows.sort(key=lambda row: (row[0], row[1]))
    print_table(["solver", "valid", "expected", "avg_resp", "max_resp", "avg_delay",
                 "drive_min", "veh_used", "wins", "secs"], [row[2] for row in rows])


def detail(results: list[Result], inputs: list[Path]) -> None:
    for path in inputs:
        rows = []
        for r in (r for r in results if r.input == path.stem):
            m = r.check.metrics if r.status == "ok" else None
            rows.append([
                r.solver,
                r.status,
                {None: "-", True: "match", False: "DIFF"}[r.matches_expected],
                f"{m.avg_response:.2f}" if m else "-",
                str(m.max_response) if m else "-",
                str(m.total_drive) if m else "-",
                str(m.vehicles_used) if m else "-",
            ])
        if rows:
            print(f"\n== {path.stem} ==")
            print_table(["solver", "status", "expected", "avg_resp", "max_resp", "drive_min", "veh_used"], rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solver", action="append", default=[], metavar="NAME=COMMAND",
                    help="add a solver (repeatable); {input} is replaced by the input path")
    ap.add_argument("--only", help="comma-separated solver names to run")
    ap.add_argument("--inputs", nargs="+", help="input file globs (default: inputs/*.txt inputs/generated/*.txt)")
    ap.add_argument("--detail", action="store_true", help="show a table for each input")
    ap.add_argument("--sort", default="avg_response", choices=SORT_KEYS, help="summary sort order")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds per run (default 10)")
    args = ap.parse_args()

    solvers = load_solvers()
    for spec in args.solver:
        name, sep, command = spec.partition("=")
        if not sep:
            ap.error(f"--solver must look like NAME=COMMAND, got {spec!r}")
        solvers[name.strip()] = command.strip()
    if args.only:
        wanted = args.only.split(",")
        missing = [w for w in wanted if w not in solvers]
        if missing:
            ap.error(f"unknown solver(s) {', '.join(missing)}; known: {', '.join(solvers) or 'none'}")
        solvers = {name: solvers[name] for name in wanted}
    if not solvers:
        ap.error("no solvers configured; add 'name = command' lines to solvers.txt or use --solver")

    inputs = sorted({Path(p) for pattern in (args.inputs or DEFAULT_INPUTS) for p in glob.glob(pattern)})
    usable = []
    for path in inputs:
        try:
            read_input(str(path))
            usable.append(path)
        except InputError as e:
            print(f"skipping {path.name}: {e}", file=sys.stderr)
    if not usable:
        ap.error("no input files found (generate some with: python3 tools/generate_inputs.py)")

    results = [run_one(name, command, path, args.timeout) for path in usable for name, command in solvers.items()]

    print(f"{len(solvers)} solvers x {len(usable)} inputs\n")
    summarize(results, list(solvers), args.sort)
    if args.detail:
        detail(results, usable)

    failures = [r for r in results if r.status != "ok"]
    if failures:
        print(f"\n{len(failures)} failed runs (details: python3 check.py <input> .bench_out/<solver>/<input>.out):")
        for r in failures:
            print(f"  {r.solver} on {r.input}: {r.status}: {r.detail}")
    print("\navg_resp/max_resp: minutes from call to job start | avg_delay: minutes beyond a free vehicle "
          "leaving base\ndrive_min: total fleet driving | wins: inputs where it had the best avg_resp "
          "| metrics count valid runs only")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
