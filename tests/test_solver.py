import itertools
import random
from pathlib import Path

import pytest

from solver.__main__ import MODES, make_algorithm
from solver.engine import run
from solver.model import Call, parse_input
from solver.render import render
from tester.checker import check

INPUTS = Path(__file__).resolve().parent.parent / "inputs"
ALL_INPUTS = sorted(INPUTS.glob("*.txt")) + sorted((INPUTS / "generated").glob("*.txt"))


def solve(text: str, mode: str) -> list[str]:
    n, calls = parse_input(text)
    return render(run(n, calls, make_algorithm(mode)))


def assert_valid(text: str, output: list[str]):
    from tester.inputs import parse_input as tester_parse
    n, calls = tester_parse(text)
    result = check(n, calls, "\n".join(output))
    assert result.errors == [], result.errors


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("name", ["brief_2_vehicles", "brief_1_vehicle", "brief_small"])
def test_matches_brief_examples(mode, name):
    out = solve((INPUTS / f"{name}.txt").read_text(), mode)
    assert out == (INPUTS / f"{name}.expected").read_text().splitlines()


@pytest.mark.parametrize("mode", MODES)
def test_valid_on_all_inputs(mode):
    for path in ALL_INPUTS:
        text = path.read_text()
        assert_valid(text, solve(text, mode))


def _random_text(rng: random.Random) -> str:
    k = rng.randint(1, 4)
    lines = [str(k)]
    for _ in range(rng.randint(0, 18)):
        t = rng.randint(8 * 60, 8 * 60 + rng.choice([30, 120, 600]))
        y, x = rng.randint(-12, 12), rng.randint(-12, 12)
        lines.append(f"{t // 60:02d}:{t % 60:02d} {abs(y)} {'N' if y >= 0 else 'S'} "
                     f"{abs(x)} {'E' if x >= 0 else 'W'} {rng.randint(0, 40)}")
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("mode", MODES)
def test_valid_on_random_inputs(mode):
    rng = random.Random(f"fuzz-{mode}")
    for _ in range(150):
        text = _random_text(rng)
        assert_valid(text, solve(text, mode))


def test_call_exactly_when_job_finishes_chains_directly():
    out = solve("1\n10:00 5 E 10\n10:15 3 N 5 E 5\n", "greedy")
    assert out[3:6] == ["Vehicle 0: 10:15 Finish job", "Vehicle 0: 10:15 Start route to job",
                        "Vehicle 0: 10:15 Drive 3 minutes north"]


def test_greedy_chains_onto_busy_vehicle_when_faster():
    # V0 finishes at 10 E at 10:20 and reaches 11 E at 10:21; V1 from base would arrive 10:26.
    out = solve("2\n10:00 10 E 10\n10:15 11 E 5\n", "greedy")
    assert "Vehicle 0: 10:20 Start route to job" in out


def test_closest_idle_waits_for_a_free_vehicle_and_serves_oldest_first():
    # One vehicle busy until 11:00 at base; calls at 10:50 (20 E) and 10:51 (1 E).
    out = solve("1\n10:00 0 N 60\n10:50 20 E 10\n10:51 1 E 10\n", "closest_idle")
    assert "Vehicle 0: 11:00 Drive 20 minutes east" in out


def test_nearest_neighbor_serves_closest_waiting_call_first():
    out = solve("1\n10:00 0 N 60\n10:50 20 E 10\n10:51 1 E 10\n", "nearest_neighbor")
    assert "Vehicle 0: 11:00 Drive 1 minutes east" in out


def test_hungarian_beats_nearest_neighbor_matching():
    # Free vehicles at 0 E and 3 E, waiting calls at 2 E and 6 E.
    # Nearest neighbour grabs the closest pair (3E->2E, 1) then 0E->6E (6): total 7.
    # Hungarian finds 0E->2E (2) + 3E->6E (3): total 5.
    from solver.engine import Vehicle
    from solver.model import Point
    from solver.algorithms import Hungarian, NearestNeighbor

    def setup():
        vs = [Vehicle(0), Vehicle(1)]
        vs[0].home_from, vs[1].home_from = Point(0, 0), Point(3, 0)
        for v in vs:
            v.home_since = 100
        calls = [Call(0, 90, Point(2, 0), 5), Call(1, 91, Point(6, 0), 5)]
        return vs, calls

    def total(pairs):
        return sum(abs(v.position(100).x - c.location.x) for v, c in pairs)

    vs, calls = setup()
    assert total(NearestNeighbor().match(100, vs, list(calls))) == 7
    vs, calls = setup()
    assert total(Hungarian().match(100, vs, list(calls))) == 5


def test_hungarian_matches_brute_force():
    from solver.algorithms.hungarian import hungarian
    rng = random.Random(3)
    for _ in range(200):
        r, c = rng.randint(1, 5), rng.randint(1, 5)
        cost = [[rng.randint(0, 20) for _ in range(c)] for _ in range(r)]
        pairs = hungarian(cost)
        assert len(pairs) == min(r, c)
        assert len({i for i, _ in pairs}) == len({j for _, j in pairs}) == len(pairs)
        got = sum(cost[i][j] for i, j in pairs)
        if r <= c:
            best = min(sum(cost[i][perm[i]] for i in range(r)) for perm in itertools.permutations(range(c), r))
        else:
            best = min(sum(cost[perm[j]][j] for j in range(c)) for perm in itertools.permutations(range(r), c))
        assert got == best
