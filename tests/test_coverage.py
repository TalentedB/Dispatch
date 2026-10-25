import itertools

import pytest

from tester.checker import check
from tester.inputs import BASE, Point, parse_input
from dispatch.coverage import CoverageConfig, coverage_metrics, expanded_bounds, plan_coverage
from dispatch.model import Status
from dispatch.optimizer import SolverConfig
from dispatch.simulation import SimulationConfig, simulate


@pytest.mark.parametrize("objective", ["center", "median"])
@pytest.mark.parametrize("fleet", [1, 2, 3])
def test_coverage_matches_exhaustive_small_grid(objective, fleet):
    config = CoverageConfig((-1, 2, -1, 1), objective, 0, 0, 0, 0, 5)
    points = config.points()
    p = plan_coverage({v: BASE for v in range(fleet)}, config)
    best = min(coverage_metrics(points, list(s))[0 if objective == "center" else 1]
               for s in itertools.combinations(points, fleet))
    assert (p.radius if objective == "center" else p.average) == pytest.approx(best)
    assert p.status == "OPTIMAL_ENUMERATION"


def test_relocation_cost_and_hysteresis_prevent_unnecessary_moves():
    config = CoverageConfig((0, 4, 0, 0), relocation_weight=100, time_limit=3)
    p = plan_coverage({0: BASE}, config)
    assert p.targets == {0: BASE} and not p.improved
    p = plan_coverage({0: Point(2, 0)}, CoverageConfig((0, 4, 0, 0), time_limit=3))
    assert not p.improved


def test_more_vehicles_than_sites_and_deterministic_assignment():
    cfg = CoverageConfig((3, 3, 0, 0), relocation_weight=0, min_improvement=0, time_limit=3)
    p = plan_coverage({0: BASE, 1: BASE}, cfg)
    assert p.targets == {0: Point(3, 0), 1: Point(3, 0)}
    assert plan_coverage({0: BASE, 1: BASE}, cfg).targets == p.targets


def test_coverage_timeout_falls_back_without_teleportation():
    p = plan_coverage({0: BASE}, CoverageConfig(time_limit=0))
    assert p.targets == {0: BASE} and p.status.startswith("FALLBACK")


def test_emergency_interrupts_initial_staging_at_actual_position():
    n, calls = parse_input("1\n00:02 5 W 1\n")
    cfg = SimulationConfig(staging=True, solver=SolverConfig(3),
                           coverage=CoverageConfig((5, 7, 0, 0), relocation_weight=0,
                                                   deployment_weight=0, time_limit=3))
    result = simulate(n, calls, cfg)
    assert result.emergencies[0].start == 9  # at x=2 when call arrives, then 7 west
    assert any(m.kind == Status.REPOSITIONING and m.end == 2 and m.destination == Point(2, 0)
               for m in result.movements)
    assert check(n, calls, result.output, allow_reposition=True).valid
    assert not check(n, calls, result.output).valid


def test_dynamic_redeployment_after_dispatch_and_release():
    n, calls = parse_input("3\n00:20 8 E 12\n01:00 3 W 1\n")
    cfg = SimulationConfig(staging=True, solver=SolverConfig(3),
                           coverage=CoverageConfig((0, 6, 0, 1), relocation_weight=0.05,
                                                   min_improvement=0, cooldown=2, time_limit=3))
    result = simulate(n, calls, cfg)
    assert len(result.coverage) >= 3
    assert any(len(p.targets) == 2 for p in result.coverage)
    assert sum(len(p.targets) == 3 for p in result.coverage) >= 2
    assert any(m.kind == Status.REPOSITIONING and m.start == 20 for m in result.movements)
    assert check(n, calls, result.output, allow_reposition=True).valid
    for e in result.emergencies.values():
        assert not any(m.vehicle == e.vehicle and m.kind == Status.REPOSITIONING
                       and m.start < e.completion and m.end > e.start for m in result.movements)


def test_staging_can_improve_response_and_is_measurable():
    n, calls = parse_input("1\n00:20 10 E 1\n")
    plain = simulate(n, calls, SimulationConfig(staging=False, solver=SolverConfig(3)))
    staged = simulate(n, calls, SimulationConfig(staging=True, solver=SolverConfig(3),
                       coverage=CoverageConfig((0, 10, 0, 0), relocation_weight=0,
                                               deployment_weight=0, time_limit=3)))
    assert staged.metrics()["total_response"] < plain.metrics()["total_response"]
    assert staged.metrics()["relocation_travel"] > 0


def test_strategy4_is_default_and_rests_away_from_base():
    n, calls = parse_input("1\n00:20 10 E 1\n01:00 10 E 1\n")
    config = SimulationConfig(solver=SolverConfig(3),
                              coverage=CoverageConfig((0, 10, 0, 0), time_limit=3))
    assert config.staging and config.scheduler == "milp"
    result = simulate(n, calls, config)
    first, second = result.emergencies.values()
    assert first.start == 25 and second.start == 65
    assert any(m.kind == Status.REPOSITIONING and m.start == first.completion
               for m in result.movements)
    assert not any(m.kind == Status.RETURNING_TO_BASE and m.start < second.completion
                   for m in result.movements)
    assert check(n, calls, result.output, allow_reposition=True).valid


def test_checker_rejects_invalid_staging_arrival_and_committed_override():
    n, calls = parse_input("1\n00:10 1 E 2\n")
    text = "Vehicle 0: 00:00 Start route to staging\nVehicle 0: 00:00 Drive 3 minutes east\nVehicle 0: 00:02 Arrive at staging\n"
    assert not check(n, calls, text, allow_reposition=True).valid
    text = "Vehicle 0: 00:10 Start route to job\nVehicle 0: 00:10 Drive 1 minutes east\nVehicle 0: 00:10 Start route to staging\n"
    assert not check(n, calls, text, allow_reposition=True).valid


def test_grid_planner_does_not_use_a_milp_solver(monkeypatch):
    import dispatch.optimizer as optimizer
    def forbidden():
        raise AssertionError("coverage must not invoke HiGHS")
    monkeypatch.setattr(optimizer, "new_solver", forbidden)
    config = CoverageConfig(enumeration_limit=0)
    positions = {0: BASE, 1: BASE, 2: BASE}
    first = plan_coverage(positions, config)
    second = plan_coverage(positions, config)
    assert first.status == "HEURISTIC" and first.gap is None
    assert first.targets == second.targets
    assert first.radius == coverage_metrics(config.points(), list(first.targets.values()))[0]
    assert sum(first.area_shares.values()) == pytest.approx(100)


def test_equal_distance_coverage_area_is_shared_fairly():
    plan = plan_coverage({0: BASE, 1: BASE}, CoverageConfig(relocation_weight=100))
    assert plan.area_shares == {0: 50, 1: 50}


def test_two_resting_vehicles_escape_clustered_coverage_plateau():
    plan = plan_coverage({0: BASE, 1: BASE}, CoverageConfig())
    assert plan.radius == 7
    assert min(plan.area_shares.values()) >= 40


@pytest.mark.parametrize("mode", ["online", "offline"])
def test_map_expands_only_when_report_events_occur(mode):
    n, calls = parse_input("2\n00:05 20 E 10\n01:00 30 N 40 W 1\n")
    result = simulate(n, calls, SimulationConfig(mode=mode, solver=SolverConfig(2),
                      coverage=CoverageConfig((0, 9, 0, 0), cooldown=0)))
    assert result.map_history == [
        {"time": 0, "bounds": (0, 9, 0, 0)},
        {"time": 5, "bounds": (0, 20, 0, 0)},
        {"time": 60, "bounds": (-40, 20, 0, 30)},
    ]
    for plan in result.coverage:
        expected = next(item["bounds"] for item in reversed(result.map_history)
                        if item["time"] <= plan.time)
        assert plan.bounds == expected
    assert check(n, calls, result.output, allow_reposition=True).valid
    # The second call cannot divert the ambulance while serving the first.
    first = result.emergencies[0]
    assert not any(m.vehicle == first.vehicle and m.kind == Status.REPOSITIONING
                   and m.start < first.completion and m.end > first.start for m in result.movements)


def test_unreported_outlier_does_not_affect_initial_deployment():
    n, calls = parse_input("2\n00:20 10 E 1\n01:00 100 N 100 W 1\n")
    config = SimulationConfig(solver=SolverConfig(2), coverage=CoverageConfig((0, 9, 0, 0)))
    full = simulate(n, calls, config)
    prefix = simulate(n, calls[:1], config)
    initial = lambda r: [(m.vehicle, m.start, m.origin, m.destination, m.end)
                         for m in r.movements if m.end < 20]
    assert initial(full) == initial(prefix)


def test_expanding_map_cannot_redirect_an_accepted_emergency():
    n, calls = parse_input("1\n00:00 5 E 10\n00:01 20 W 1\n")
    result = simulate(n, calls, SimulationConfig(solver=SolverConfig(2)))
    first, second = result.emergencies.values()
    assert first.start == 5 and first.completion == 15
    assert second.start == 40
    assert result.map_history[1] == {"time": 1, "bounds": (-20, 9, 0, 9)}
    assert check(n, calls, result.output, allow_reposition=True).valid


def test_large_map_uses_bounded_weighted_samples():
    config = CoverageConfig((-10**9, 10**9, -10**9, 10**9),
                            max_candidates=25, max_demand_points=100, enumeration_limit=0)
    plan = plan_coverage({0: BASE, 1: BASE}, config)
    assert plan.sampled and plan.demand_points <= 100
    assert plan.candidate_count <= 28
    assert sum(plan.area_shares.values()) == pytest.approx(100)
    assert expanded_bounds(config.bounds, Point(0, 0)) == config.bounds


def test_exhausted_run_budget_skips_coverage_but_keeps_reported_map():
    n, calls = parse_input("1\n00:01 20 W 1\n")
    result = simulate(n, calls, SimulationConfig(runtime_limit=0))
    assert not result.coverage
    assert result.metrics()["coverage_skipped_budget"] > 0
    assert result.map_history[-1] == {"time": 1, "bounds": (-20, 9, 0, 9)}
    assert check(n, calls, result.output, allow_reposition=True).valid
