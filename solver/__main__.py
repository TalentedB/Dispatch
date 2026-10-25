"""Emergency vehicle dispatcher.

    python3 -m solver input.txt                       # default: greedy
    python3 -m solver input.txt --mode hungarian

Modes:
  greedy            vehicle that can arrive soonest, including busy ones (job is chained)
  closest_idle      closest free vehicle; if none, calls wait and are served oldest-first
  nearest_neighbor  closest free vehicle; a vehicle that frees up takes the closest waiting call
  hungarian         free vehicles and waiting calls matched to minimise total distance
"""

from __future__ import annotations

import argparse
import sys

from .engine import run
from .model import InputError, parse_input
from .algorithms import ALGORITHMS
from .render import render

MODES = list(ALGORITHMS)


def make_algorithm(mode: str):
    return ALGORITHMS[mode]()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m solver", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="input file, or - for stdin")
    ap.add_argument("--mode", choices=MODES, default="greedy")
    args = ap.parse_args(argv)

    try:
        text = sys.stdin.read() if args.input == "-" else open(args.input).read()
        num_vehicles, calls = parse_input(text)
    except (OSError, InputError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("\n".join(render(run(num_vehicles, calls, make_algorithm(args.mode)))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
