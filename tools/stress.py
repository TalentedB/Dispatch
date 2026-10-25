"""Stress-test and compare solver modes on many random scenarios, in-process.

    python3 tools/stress.py                  # 150 scenarios per load level
    python3 tools/stress.py --n 500 --seed 2

Every output is validated by tester/checker.py. For each load level and
mode it reports average/worst response, driving, runtime, and how often the
output differs from greedy (our best guess at the judges' reference
algorithm), which is the risk if hidden tests are compared line for line.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solver.engine import run  # noqa: E402
from solver.model import parse_input  # noqa: E402
from solver.algorithms import ALGORITHMS, Greedy  # noqa: E402
from solver.render import render  # noqa: E402
from tester.checker import check  # noqa: E402
from tester.inputs import parse_input as checker_parse  # noqa: E402

VARIANTS = ALGORITHMS  # name -> algorithm class

# Load levels: (calls, window minutes over which they arrive)
LEVELS = {
    "light": ((5, 20), 12 * 60),
    "medium": ((10, 30), 4 * 60),
    "heavy": ((15, 40), 90),
}


def scenario(rng: random.Random, level: str) -> str:
    (lo, hi), window = LEVELS[level]
    k = rng.randint(1, 6)
    radius = rng.randint(5, 25)
    start = rng.randint(6 * 60, 12 * 60)
    lines = [str(k)]
    for _ in range(rng.randint(lo, hi)):
        t = start + rng.randint(0, window)
        y, x = rng.randint(-radius, radius), rng.randint(-radius, radius)
        lines.append(f"{t // 60:02d}:{t % 60:02d} {abs(y)} {'N' if y >= 0 else 'S'} "
                     f"{abs(x)} {'E' if x >= 0 else 'W'} {rng.randint(5, 60)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=150, help="scenarios per load level")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--modes", help="comma-separated subset of: " + ", ".join(VARIANTS))
    args = ap.parse_args()
    modes = args.modes.split(",") if args.modes else list(VARIANTS)

    invalid = 0
    for level in LEVELS:
        rng = random.Random(f"{args.seed}-{level}")
        texts = [scenario(rng, level) for _ in range(args.n)]
        stats = {m: {"resp": 0, "calls": 0, "max": 0, "drive": 0, "secs": 0.0, "differs": 0, "best": 0}
                 for m in modes}
        for text in texts:
            n, calls = parse_input(text)
            cn, ccalls = checker_parse(text)
            outputs, avgs = {}, {}
            for m in modes:
                t0 = time.perf_counter()
                out = render(run(n, calls, VARIANTS[m]()))
                stats[m]["secs"] += time.perf_counter() - t0
                result = check(cn, ccalls, "\n".join(out))
                if result.errors:
                    invalid += 1
                    print(f"INVALID {m} on {level}:\n{text}\n{result.errors[:3]}", file=sys.stderr)
                    continue
                mt = result.metrics
                s = stats[m]
                s["resp"] += mt.avg_response * mt.calls_served
                s["calls"] += mt.calls_served
                s["max"] = max(s["max"], mt.max_response)
                s["drive"] += mt.total_drive
                outputs[m], avgs[m] = out, mt.avg_response
            reference = render(run(n, calls, Greedy()))
            best = min(avgs.values()) if avgs else 0
            for m in outputs:
                stats[m]["differs"] += outputs[m] != reference
                stats[m]["best"] += avgs[m] == best

        base = stats[modes[0]]
        print(f"\n== {level}: {args.n} scenarios ==")
        header = f"{'mode':<17} {'avg_resp':>9} {'vs ' + modes[0]:>13} {'max_resp':>9} {'drive':>8} " \
                 f"{'best':>5} {'differs':>8} {'ms/run':>7}"
        print(header)
        print("-" * len(header))
        for m in modes:
            s = stats[m]
            avg = s["resp"] / max(s["calls"], 1)
            base_avg = base["resp"] / max(base["calls"], 1)
            change = f"{(avg - base_avg) / base_avg * 100:+.1f}%" if base_avg else "-"
            print(f"{m:<17} {avg:>9.2f} {change:>13} {s['max']:>9} {s['drive']:>8} {s['best']:>5} "
                  f"{s['differs'] / args.n * 100:>7.0f}% {s['secs'] / args.n * 1000:>7.1f}")

    print(f"\n{'all outputs valid' if not invalid else f'{invalid} INVALID outputs'}")
    print("best = scenarios where the mode tied for lowest avg response; "
          "differs = output not identical to greedy")
    return 1 if invalid else 0


if __name__ == "__main__":
    sys.exit(main())
