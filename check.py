"""Check one solver output against its input, with full error details.

    python3 check.py inputs/brief_small.txt my_output.txt
    python3 my_solver.py inputs/brief_small.txt | python3 check.py inputs/brief_small.txt -

Prints every rule violation, the metrics, and a diff against the .expected
file if there is one. Exits 0 if the output is valid.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tester.checker import check, fmt_time
from tester.inputs import InputError, read_input
from tester.runner import expected_diff, matches_expected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="input file the solver was given")
    ap.add_argument("output", help="solver output file, or - for stdin")
    args = ap.parse_args()

    try:
        num_vehicles, calls = read_input(str(args.input))
        output = sys.stdin.read() if args.output == "-" else Path(args.output).read_text()
    except (OSError, InputError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    result = check(num_vehicles, calls, output)
    if result.valid:
        print("VALID")
    else:
        print(f"INVALID ({len(result.errors)} problems):")
        for e in result.errors:
            print(f"  - {e}")

    m = result.metrics
    print(f"\ncalls served:  {m.calls_served}/{len(calls)}")
    print(f"avg response:  {m.avg_response:.2f} min (max {m.max_response})")
    print(f"avg delay:     {m.avg_delay:.2f} min beyond a free vehicle leaving base")
    print(f"total driving: {m.total_drive} min")
    print(f"vehicles used: {m.vehicles_used}/{num_vehicles}")
    if m.last_return:
        print(f"last return:   {fmt_time(m.last_return)}")

    match = matches_expected(output, args.input)
    if match is True:
        print("\nmatches expected output")
    elif match is False:
        print("\ndiffers from expected output:")
        print("\n".join(expected_diff(output, args.input)))
    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
