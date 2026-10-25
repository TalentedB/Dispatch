"""Generates random test inputs for the benchmark.

    python tools/generate_inputs.py              # writes inputs/generated/*.txt
    python tools/generate_inputs.py --seeds 5    # more variations per scenario

Output is deterministic for a given seed, so everyone on the team benchmarks
against the same files.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Scenario:
    name: str
    vehicles: int
    calls: int
    start: str  # HH:MM, earliest call
    end: str  # HH:MM, latest call
    radius: int  # max blocks from base on each axis
    duration: tuple[int, int]  # min/max job minutes
    hotspots: int = 0  # >0: calls cluster around this many points
    one_axis: bool = False  # all calls due east (tests chaining along a line)


SCENARIOS = [
    Scenario("light_day", vehicles=3, calls=20, start="08:00", end="20:00", radius=25, duration=(10, 60)),
    Scenario("rush_hour", vehicles=3, calls=30, start="17:00", end="19:00", radius=20, duration=(15, 45)),
    Scenario("overloaded", vehicles=2, calls=40, start="09:00", end="13:00", radius=20, duration=(10, 40)),
    Scenario("clustered", vehicles=4, calls=30, start="10:00", end="16:00", radius=30, duration=(10, 30), hotspots=3),
    Scenario("one_axis", vehicles=2, calls=15, start="09:00", end="12:00", radius=20, duration=(5, 20), one_axis=True),
    Scenario("single_vehicle", vehicles=1, calls=15, start="08:00", end="18:00", radius=15, duration=(10, 40)),
    Scenario("big_fleet", vehicles=10, calls=80, start="06:00", end="22:00", radius=40, duration=(10, 90)),
    Scenario("burst", vehicles=3, calls=12, start="14:00", end="14:05", radius=15, duration=(5, 30)),
]


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _format_call(time: int, x: int, y: int, duration: int) -> str:
    parts = [f"{time // 60:02d}:{time % 60:02d}"]
    if y or not x:
        parts.append(f"{abs(y)} {'N' if y >= 0 else 'S'}")
    if x:
        parts.append(f"{abs(x)} {'E' if x > 0 else 'W'}")
    parts.append(str(duration))
    return " ".join(parts)


def generate(scenario: Scenario, seed: int) -> str:
    rng = random.Random(f"{scenario.name}-{seed}")
    r = scenario.radius
    hotspots = [(rng.randint(-r, r), rng.randint(-r, r)) for _ in range(scenario.hotspots)]

    calls = []
    for _ in range(scenario.calls):
        time = rng.randint(_minutes(scenario.start), _minutes(scenario.end))
        if scenario.one_axis:
            x, y = rng.randint(1, r), 0
        elif hotspots:
            hx, hy = rng.choice(hotspots)
            x, y = hx + rng.randint(-3, 3), hy + rng.randint(-3, 3)
        else:
            x, y = rng.randint(-r, r), rng.randint(-r, r)
        calls.append((time, x, y, rng.randint(*scenario.duration)))

    calls.sort(key=lambda c: c[0])
    lines = [str(scenario.vehicles)] + [_format_call(*c) for c in calls]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=3, help="variations per scenario (default 3)")
    ap.add_argument("--out", type=Path, default=ROOT / "inputs" / "generated")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for scenario in SCENARIOS:
        for seed in range(1, args.seeds + 1):
            path = args.out / f"{scenario.name}_{seed}.txt"
            path.write_text(generate(scenario, seed))
    print(f"wrote {len(SCENARIOS) * args.seeds} files to {args.out}")


if __name__ == "__main__":
    main()
