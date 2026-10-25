"""Collect solver diagnostics using the EXISTING benchmark runner and validator.

python -m tools.benchmark_dispatch --output .bench_out/metrics.json
python -m tools.benchmark_dispatch --inputs "inputs/generated/*.txt"
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import glob
import json
from pathlib import Path
import sys

from bench import run_one, summarize
from dispatch.coverage import CoverageConfig
from dispatch.optimizer import SolverConfig


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inputs", nargs="+", default=["inputs/brief_*.txt", "tests/fixtures/duration_order.txt",
                                                   "tests/fixtures/coverage_line.txt"])
    ap.add_argument("--output", type=Path, default=Path(".bench_out/metrics.json"))
    ap.add_argument("--time-limit", type=float, default=SolverConfig().time_limit)
    ap.add_argument("--coverage-time-limit", type=float, default=CoverageConfig().time_limit)
    ap.add_argument("--timeout", type=float, default=20)
    ap.add_argument("--run-time-limit", type=float, default=20)
    ap.add_argument("--workers", type=int, default=1,
                    help="independent solver subprocesses (default: 1)")
    ap.add_argument("--variants", default="greedy,milp,strategy4")
    ap.add_argument("--bounds", nargs=4, type=int, default=CoverageConfig().bounds)
    args = ap.parse_args()
    if args.workers < 1:
        ap.error("workers must be positive")
    staging = ("--staging --bounds " + " ".join(map(str, args.bounds))
               + f" --coverage-time-limit {args.coverage_time_limit}")
    variants = {"greedy": "--scheduler greedy --no-staging", "milp": "--no-staging",
                "offline": "--mode offline --no-staging", "staged": staging,
                "strategy4": staging, "greedy-staged": "--scheduler greedy " + staging}
    wanted = args.variants.split(",")
    if set(wanted) - set(variants):
        ap.error("unknown variant")
    variants = {name: variants[name] for name in wanted}
    paths = sorted({Path(p) for pattern in args.inputs for p in glob.glob(pattern)})
    if not paths:
        ap.error("no inputs matched")
    report_dir = args.output.parent / (args.output.stem + "-solver-reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    def run_case(path, name, options):
        report = report_dir / f"{name}-{path.stem}.json"
        if report.exists():
            report.unlink()  # avoid reading a stale report after a crash
        command = (f'"{Path(sys.executable).as_posix()}" -m dispatch {{input}} {options} '
                   f'--time-limit {args.time_limit} --run-time-limit {args.run_time_limit} '
                   f'--report "{report.as_posix()}"')
        print(f"Starting {name} on {path}", file=sys.stderr, flush=True)
        result = run_one(name, command, path, args.timeout,
                         allow_reposition=name in ("staged", "strategy4", "greedy-staged"))
        detail = json.loads(report.read_text()) if result.status == "ok" and report.exists() else {}
        row = {"solver": name, "input": str(path), "status": result.status,
               "time_limit": args.time_limit, "coverage_time_limit": args.coverage_time_limit,
               "simulation_timeout": args.timeout, "workers": args.workers,
               "run_time_limit": args.run_time_limit,
               "bounds": args.bounds, "wall_seconds": result.seconds, "error": result.detail,
               "metrics": detail.get("metrics"),
               "map_history": detail.get("map_history", []),
               "optimizations": [{k: p[k] for k in
                                  ("status", "objective", "gap", "seconds", "primary_optimal",
                                   "lexicographic_optimal", "fallback_reason", "stage_statuses",
                                   "algorithm", "incumbent_source", "model_build_seconds", "dp_states",
                                   "allowance_seconds")}
                                 for p in detail.get("optimizations", [])],
               "coverage": detail.get("coverage", [])}
        metric = detail.get("metrics", {})
        print(f"Finished {name} on {path}: {result.status}; "
              f"response={metric.get('total_response', 'unavailable')}; "
              f"wall={result.seconds:.2f}s", file=sys.stderr, flush=True)
        return result, row

    results, data = [], []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        tasks = [executor.submit(run_case, path, name, options)
                 for path in paths for name, options in variants.items()]
        for task in as_completed(tasks):
            result, row = task.result()
            results.append(result)
            data.append(row)
            data.sort(key=lambda item: (item["input"], item["solver"]))
            # Persist each completed run so long quality-focused comparisons
            # retain diagnostics and are inspectable before the batch finishes.
            args.output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    args.output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    summarize(results, list(variants), "avg_response")
    return int(any(r.status != "ok" for r in results))


if __name__ == "__main__":
    raise SystemExit(main())
