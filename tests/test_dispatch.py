"""Extend the existing pytest and replay checker, including exhaustive oracles."""
import itertools
from pathlib import Path
import random
from types import SimpleNamespace

import pytest

from tester.checker import check
from tester.inputs import BASE, Call, Point, manhattan, parse_input, read_input
from dispatch.model import Anchor, Movement, Status
from dispatch.optimizer import SolverConfig, greedy, optimize
from dispatch.simulation import SimulationConfig, simulate
from dispatch.validation import validate_plan

ROOT = Path(__file__).resolve().parents[1]


def exhaustive(calls, anchors, now):
    """Enumerate permutations and weak route partitions; no model/extractor reuse."""
    best = None
    for order in itertools.permutations(calls):
        for cuts in itertools.combinations_with_replacement(range(len(calls) + 1), len(anchors) - 1):
            boundaries = (0, *cuts, len(calls))
            response, travel, used = [], 0, 0
            for a, lo, hi in zip(anchors, boundaries, boundaries[1:]):
                time, position = max(now, a.available), a.position
                used += hi > lo
                for c in order[lo:hi]:
                    distance = abs(position.x - c.location.x) + abs(position.y - c.location.y)
                    start = max(time, c.time) + distance
                    response.append(start - c.time)
                    travel += distance
                    time, position = start + c.duration, c.location
                travel += abs(position.x) + abs(position.y)
            score = (sum(response), max(response, default=0), travel, used)
            best = score if best is None else min(best, score)
    return best


@pytest.mark.parametrize("fleet", [1, 2, 3])
@pytest.mark.parametrize("seed", range(4))
def test_milp_matches_independent_enumeration(fleet, seed):
    rng = random.Random(seed)
    calls = [Call(i, rng.randrange(4), Point(rng.randrange(-2, 3), rng.randrange(-2, 3)),
                  rng.randrange(5)) for i in range(4)]
    anchors = [Anchor(v, Point(v, -v), v) for v in range(fleet)]
    plan = optimize(calls, anchors, 0, SolverConfig(5))
    assert plan.lexicographic_optimal, plan
    assert (plan.total_response, plan.max_response, plan.travel,
            sum(bool(r) for r in plan.routes.values())) == exhaustive(calls, anchors, 0)
    validate_plan(plan, calls, anchors, 0)


def test_service_duration_changes_optimal_order_and_beats_greedy():
    calls = [Call(0, 0, Point(1, 0), 100), Call(1, 0, Point(2, 0), 0)]
    anchors = [Anchor(0, BASE, 0)]
    plan = optimize(calls, anchors, 0, SolverConfig(3))
    assert [j.call for j in plan.routes[0]] == [1, 0]
    assert plan.total_response == 5 < greedy(calls, anchors, 0).total_response == 103
    flipped = [Call(0, 0, Point(1, 0), 0), Call(1, 0, Point(2, 0), 100)]
    assert [j.call for j in optimize(flipped, anchors, 0, SolverConfig(3)).routes[0]] == [0, 1]


def test_release_time_requires_departure_after_report():
    calls = [Call(0, 10, Point(5, 0), 1), Call(1, 30, Point(9, 0), 1)]
    p = optimize(calls, [Anchor(0, BASE, 0)], 0, SolverConfig(3))
    assert p.routes[0][0].start == 15
    assert p.routes[0][1].start == 34


def test_zero_duration_colocated_jobs_have_no_subtours():
    calls = [Call(i, 0, BASE, 0) for i in range(6)]
    p = optimize(calls, [Anchor(v, BASE, 0) for v in range(2)], 0, SolverConfig(3))
    assert p.status == "OPTIMAL" and p.total_response == 0
    assert sorted(j.call for r in p.routes.values() for j in r) == list(range(6))


def test_busy_anchor_includes_locked_service_and_location():
    p = optimize([Call(0, 5, Point(-3, 4), 8)], [Anchor(0, Point(2, -1), 20)],
                 5, SolverConfig(3))
    assert p.routes[0][0].departure == 20 and p.routes[0][0].start == 30


def test_strategy4_remaining_time_is_counted_once():
    anchors = [Anchor(0, Point(1, 0), 30), Anchor(1, Point(8, 0), 20)]
    assert anchors[0].remaining(20) == 10
    call = Call(0, 15, BASE, 2)
    plan = optimize([call], anchors, 20, SolverConfig(3))
    assert not plan.routes[0]  # close but unavailable for ten more minutes
    assert plan.routes[1][0].start == 28
    assert plan.total_response == 13  # five already waited + eight travel


def test_expected_arrivals_and_completions_reuse_queued_plan(monkeypatch):
    import dispatch.simulation as module
    original, seen = module.optimize, []
    def record(calls, anchors, now, *args):
        seen.append((now, [(a.position, a.available) for a in anchors]))
        return original(calls, anchors, now, *args)
    monkeypatch.setattr(module, "optimize", record)
    result = run_text("1\n00:00 5 E 10\n00:01 6 E 1\n", solver=SolverConfig(3))
    assert [now for now, _ in seen] == [0, 1]
    assert seen[1][1] == [(Point(5, 0), 15)]
    assert result.emergencies[1].start == 16
    assert result.metrics()["reused_plans"] == 1
    assert result.metrics()["incident_solves"] == 2


def test_simultaneous_reports_are_one_solve():
    result = run_text("1\n00:00 1 E 4\n00:00 2 E 1\n00:00 3 E 2\n",
                      solver=SolverConfig(3))
    assert result.metrics()["incident_solves"] == 1
    assert result.metrics()["reused_plans"] == 2


def test_zero_whole_run_budget_preserves_locked_jobs_and_valid_output():
    result = run_text("1\n00:00 5 E 10\n00:01 20 W 1\n", runtime_limit=0)
    assert result.emergencies[0].start == 5
    assert result.emergencies[1].start == 40
    assert all(p.status == "FALLBACK" and "run computation budget" in p.fallback_reason
               for p in result.optimizations)


def test_shared_route_arcs_do_not_duplicate_with_fleet_size(monkeypatch):
    import dispatch.optimizer as module
    original, models = module.new_solver, []
    def capture():
        model = original()
        models.append(model)
        return model
    monkeypatch.setattr(module, "new_solver", capture)
    n, fleet = 4, 8
    calls = [Call(j, 0, Point(j, 0), j) for j in range(n)]
    plan = module.optimize(calls, [Anchor(v, BASE, v) for v in range(fleet)], 0, SolverConfig(3))
    assert plan.primary_optimal
    assert models[0].getNumCol() == 2*n+fleet*n+fleet+n*(n-1)+n+1


def test_travel_objective_includes_unused_vehicle_return():
    anchors = [Anchor(0, Point(100, 0), 0), Anchor(1, BASE, 0)]
    p = optimize([Call(0, 0, Point(50, 0), 0)], anchors, 0, SolverConfig(3))
    assert p.primary_optimal and p.travel == 100
    assert p.routes[0] and not p.routes[1]  # serving with vehicle 1 would travel 200


def test_zero_budget_fallback_is_explicit_and_valid():
    calls = [Call(0, 0, Point(3, 0), 1)]
    anchors = [Anchor(0, BASE, 0)]
    p = optimize(calls, anchors, 0, SolverConfig(0))
    assert p.status == "FALLBACK" and p.fallback_reason and not p.primary_optimal
    validate_plan(p, calls, anchors, 0)


@pytest.mark.parametrize("status_name", ["kInfeasible", "kTimeLimit", "kSolveError"])
def test_no_incumbent_status_never_reported_as_valid_milp(monkeypatch, status_name):
    import highspy
    import dispatch.optimizer as module
    original = module.new_solver

    class NoIncumbent:
        def __init__(self):
            self.h = original()
        def __getattr__(self, name):
            return getattr(self.h, name)
        def run(self):
            pass
        def getModelStatus(self):
            return getattr(highspy.HighsModelStatus, status_name)
        def getSolution(self):
            return SimpleNamespace(value_valid=False)

    monkeypatch.setattr(module, "new_solver", NoIncumbent)
    p = module.optimize([Call(0, 0, BASE, 0)], [Anchor(0, BASE, 0)], 0, SolverConfig(3))
    assert p.status == "FALLBACK" and not p.primary_optimal and p.fallback_reason


def test_time_limit_with_incumbent_is_feasible_not_optimal(monkeypatch):
    import highspy
    import dispatch.optimizer as module
    original = module.new_solver
    class Limited:
        def __init__(self):
            self.h = original()
        def __getattr__(self, name):
            return getattr(self.h, name)
        def getModelStatus(self):
            return highspy.HighsModelStatus.kTimeLimit
    monkeypatch.setattr(module, "new_solver", Limited)
    p = module.optimize([Call(0, 0, BASE, 0)], [Anchor(0, BASE, 0)], 0, SolverConfig(3))
    assert p.status == "FEASIBLE" and not p.primary_optimal


def test_solver_exception_fallback(monkeypatch):
    import dispatch.optimizer as module
    def broken():
        raise RuntimeError("solver unavailable")
    monkeypatch.setattr(module, "new_solver", broken)
    p = module.optimize([Call(0, 0, BASE, 0)], [Anchor(0, BASE, 0)], 0)
    assert p.status == "FALLBACK" and "unavailable" in p.fallback_reason


def run_text(text, **kwargs):
    kwargs.setdefault("staging", False)  # legacy base-return regression cases
    n, calls = parse_input(text)
    result = simulate(n, calls, SimulationConfig(**kwargs))
    checked = check(n, calls, result.output, allow_reposition=kwargs.get("staging", False))
    assert checked.valid, checked.errors
    assert result.metrics()["total_response"] == pytest.approx(checked.metrics.avg_response * len(calls))
    assert result.metrics()["total_travel"] == checked.metrics.total_drive
    return result


def test_return_redirection_matches_existing_fixture():
    result = run_text((ROOT / "inputs/brief_small.txt").read_text())
    assert result.output == (ROOT / "inputs/brief_small.expected").read_text()
    assert result.emergencies[1].start == 730


def test_queues_chaining_and_commitments():
    result = run_text("1\n12:00 5 E 10\n12:01 1 W 0\n12:02 6 E 1\n")
    assert result.emergencies[0].start == 725  # cannot divert to the closer new call
    assert result.emergencies[0].completion == 735
    assert result.emergencies[2].start == 736  # service duration + direct chain
    assert "12:15 Start route to base" not in result.output


def test_simultaneous_duplicate_locations_different_durations():
    result = run_text("1\n12:00 1 E 20\n12:00 1 E 0\n12:00 0 N 0\n")
    assert result.emergencies[1].completion < result.emergencies[0].completion


def test_online_information_boundary_and_offline_distinction(monkeypatch):
    import dispatch.simulation as module
    original = module.optimize
    seen = []
    def inspect(calls, anchors, now, *args):
        seen.append((now, [c.time for c in calls]))
        return original(calls, anchors, now, *args)
    monkeypatch.setattr(module, "optimize", inspect)
    run_text("1\n12:00 10 E 10\n12:01 1 W 1\n")
    assert all(all(t <= now for t in times) for now, times in seen)
    seen.clear()
    run_text("1\n12:00 10 E 10\n12:01 1 W 1\n", mode="offline", solver=SolverConfig(3))
    assert any(any(t > now for t in times) for now, times in seen)


def test_offline_waits_at_predecessor_and_matches_enumeration():
    n, calls = parse_input("2\n12:00 4 E 10\n12:02 2 W 1\n12:04 1 N 1\n")
    result = run_text("2\n12:00 4 E 10\n12:02 2 W 1\n12:04 1 N 1\n", mode="offline", solver=SolverConfig(4))
    assert result.metrics()["total_response"] == exhaustive(calls, [Anchor(v, BASE, 0) for v in range(n)], 0)[0]


@pytest.mark.parametrize("seed", range(3))
def test_offline_returning_vehicles_remain_physically_valid(seed):
    rng = random.Random(seed)
    calls = [Call(i, rng.randrange(0, 40), Point(rng.randrange(-6, 7), rng.randrange(-6, 7)),
                  rng.randrange(10)) for i in range(8)]
    result = simulate(3, calls, SimulationConfig(mode="offline", staging=False, solver=SolverConfig(0.1)))
    checked = check(3, calls, result.output)
    assert checked.valid, checked.errors


def test_determinism():
    text = "2\n12:00 2 N 0\n12:00 2 S 0\n12:00 0 N 0\n"
    assert run_text(text, solver=SolverConfig(3)).output == run_text(text, solver=SolverConfig(3)).output


def test_movement_position_is_not_destination():
    m = Movement(0, 10, Point(-2, -3), Point(3, 2), Status.REPOSITIONING, 20)
    assert m.position(12) == Point(0, -3)
    assert m.position(17) == Point(3, -1)
    assert m.position(100) == Point(3, 2)


@pytest.mark.parametrize("path", sorted((ROOT / "inputs").rglob("*.txt")), ids=lambda p: p.stem)
def test_shipped_scenarios_with_existing_checker(path):
    n, calls = read_input(str(path))
    # Keep the shipped-scenario correctness regression's original short budget.
    # Quality comparisons use the application defaults through the benchmark.
    result = simulate(n, calls, SimulationConfig(staging=False, solver=SolverConfig(0.25)))
    checked = check(n, calls, result.output)
    assert checked.valid, checked.errors


def test_empty_and_zero_jobs_at_base():
    assert run_text("2\n").output == ""
    run_text("1\n00:00 0 N 0\n00:00 0 N 0\n")


def test_independent_validator_rejects_corrupted_solutions():
    from dataclasses import replace
    from dispatch.validation import validate_execution
    calls = [Call(0, 0, Point(3, 0), 1)]
    anchors = [Anchor(0, BASE, 0)]
    plan = greedy(calls, anchors, 0)
    plan.routes[0][0] = replace(plan.routes[0][0], start=0)
    with pytest.raises(ValueError, match="travel"):
        validate_plan(plan, calls, anchors, 0)
    result = simulate(1, calls)
    result.movements[0] = replace(result.movements[0], origin=Point(2, 0))
    with pytest.raises(ValueError, match="teleportation"):
        validate_execution(result.emergencies, result.movements, 1)


def test_newly_free_vehicle_reconsiders_work_queued_behind_a_busy_partner(monkeypatch):
    import dispatch.simulation as simulation_module
    from dispatch.model import make_plan

    original_optimize = simulation_module.optimize
    solve_count = 0

    def feasible_first_plan(calls, anchors, now, *args):
        nonlocal solve_count
        solve_count += 1
        if solve_count == 1:
            # A legal time-limited incumbent can leave a poor future assignment.
            return make_plan({0: [0], 1: [1, 2]}, calls, anchors, now, "FEASIBLE")
        return original_optimize(calls, anchors, now, *args)

    monkeypatch.setattr(simulation_module, "optimize", feasible_first_plan)
    count, calls = parse_input("2\n00:00 2 E 1\n00:00 2 W 10\n00:00 3 E 1\n")
    result = simulate(count, calls, SimulationConfig())
    assert result.emergencies[2].vehicle == 0
    assert result.emergencies[2].start == 4
    assert any(m.vehicle == 0 and m.start == 3 and m.call == 2
               and m.kind == Status.TRAVELING_TO_EMERGENCY for m in result.movements)
    assert check(count, calls, result.output, allow_reposition=True).valid


def test_completion_reoptimizes_a_nonempty_queue_from_a_feasible_incumbent(monkeypatch):
    import dispatch.simulation as simulation_module
    from dispatch.model import make_plan

    original_optimize = simulation_module.optimize
    solve_count = 0

    def feasible_first_plan(calls, anchors, now, *args):
        nonlocal solve_count
        solve_count += 1
        if solve_count == 1:
            return make_plan({0: [0, 1, 2], 1: [3]}, calls, anchors, now, "FEASIBLE")
        return original_optimize(calls, anchors, now, *args)

    monkeypatch.setattr(simulation_module, "optimize", feasible_first_plan)
    count, calls = parse_input("2\n00:00 2 E 1\n00:00 10 E 1\n00:00 3 E 1\n00:00 0 E 50\n")
    result = simulate(count, calls, SimulationConfig())
    assert result.emergencies[2].start == 4
    assert result.emergencies[1].start == 12
    assert result.emergencies[3].completion == 50
    assert check(count, calls, result.output, allow_reposition=True).valid
