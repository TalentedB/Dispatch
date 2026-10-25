"""Independent enumeration checks for DP, retained queues, and hybrid selection."""
import itertools
import random
import pytest
from tester.inputs import BASE, Call, Point, manhattan
from dispatch.model import Anchor, plan_score
from dispatch.optimizer import SolverConfig, greedy
from dispatch.planning import optimize, retained_plan
from dispatch.validation import validate_plan


def enumerate_score(calls, anchors, now, priorities, floor):
    best = None
    for order in itertools.permutations(calls):
        for cuts in itertools.combinations_with_replacement(range(len(calls)+1), len(anchors)-1):
            edges = (0, *cuts, len(calls))
            delays, travel, used = [], 0, 0
            for anchor, lo, hi in zip(anchors, edges, edges[1:]):
                time, position = max(now, anchor.available), anchor.position
                used += hi > lo
                for call in order[lo:hi]:
                    distance = manhattan(position, call.location)
                    start = max(time, call.time)+distance
                    delays.append(start-call.time)
                    travel += distance
                    time, position = start+call.duration, call.location
                travel += manhattan(position, BASE)
            values = dict(response=sum(delays), worst=max(floor, max(delays, default=0)),
                          travel=travel, deployments=used)
            score = tuple(values[name] for name in priorities)
            best = score if best is None else min(best, score)
    return best


@pytest.mark.parametrize('fleet', [1,2,3])
@pytest.mark.parametrize('seed', range(4))
def test_dp_matches_independent_enumeration(fleet, seed):
    rng = random.Random(seed)
    calls = [Call(j, rng.randrange(6), Point(rng.randrange(-2,3), rng.randrange(-2,3)),
                  rng.randrange(6)) for j in range(4)]
    anchors = [Anchor(v, Point(v,-v), v+1) for v in range(fleet)]
    config = SolverConfig(2)
    plan = optimize(calls, anchors, 0, config)
    assert plan.status == 'DP_OPTIMAL' and plan.algorithm == 'dp'
    assert plan.primary_optimal and plan.lexicographic_optimal
    assert plan_score(plan, config.priorities) == enumerate_score(calls, anchors, 0, config.priorities, 0)
    validate_plan(plan, calls, anchors, 0)


@pytest.mark.parametrize('priorities', [
    ('response','travel','worst','deployments'),
    ('response','deployments','worst','travel'),
    ('response','worst','travel','deployments'),
])
@pytest.mark.parametrize('floor', [0,100])
def test_dp_honors_configured_priorities_and_fixed_worst_delay(priorities, floor):
    calls = [Call(0,0,Point(1,0),4), Call(1,3,Point(-2,0),0), Call(2,0,Point(2,1),1)]
    anchors = [Anchor(0,BASE,0), Anchor(1,Point(2,0),4)]
    plan = optimize(calls, anchors, 0, SolverConfig(2, priorities), floor)
    assert plan.status == 'DP_OPTIMAL'
    assert plan_score(plan, priorities, floor) == enumerate_score(calls, anchors, 0, priorities, floor)


def test_retained_queue_is_extended_and_beats_new_greedy_fallback():
    calls = [Call(0,0,Point(1,0),100), Call(1,0,Point(2,0),0), Call(2,0,Point(3,0),0)]
    anchors = [Anchor(0,BASE,0)]
    plan = optimize(calls, anchors, 0, SolverConfig(0), queues={0:[1,0]})
    assert plan.status == 'FALLBACK' and plan.incumbent_source == 'retained'
    assert plan.total_response < greedy(calls, anchors, 0).total_response
    assert sorted(j.call for j in plan.routes[0]) == [0,1,2]
    validate_plan(plan, calls, anchors, 0)


def test_solver_failure_keeps_retained_incumbent(monkeypatch):
    import dispatch.optimizer as module
    def broken():
        raise RuntimeError('unavailable')
    monkeypatch.setattr(module, 'new_solver', broken)
    calls = [Call(0,0,Point(1,0),100), Call(1,0,Point(2,0),0)]
    plan = optimize(calls, [Anchor(0,BASE,0)], 0, SolverConfig(1, dp_limit=0), queues={0:[1,0]})
    assert plan.status == 'FALLBACK' and plan.incumbent_source == 'retained'
    assert plan.total_response == 5 and not plan.primary_optimal


def test_dp_respects_locked_completion_anchor_and_no_advance_dispatch():
    calls = [Call(0,5,Point(4,0),2), Call(1,30,Point(5,0),0)]
    anchors = [Anchor(0,Point(2,0),20)]
    plan = optimize(calls, anchors, 5, SolverConfig(2))
    assert plan.status == 'DP_OPTIMAL'
    validate_plan(plan, calls, anchors, 5)
    assert plan.routes[0][0].departure >= 20
    assert all(job.departure >= calls[job.call].time for job in plan.routes[0])


def test_dp_zero_duration_duplicates_are_assigned_once():
    calls = [Call(j,0,BASE,0) for j in range(6)]
    plan = optimize(calls, [Anchor(0,BASE,0),Anchor(1,BASE,0)], 0, SolverConfig(2))
    assert plan.status == 'DP_OPTIMAL' and plan.total_response == 0
    assert sorted(j.call for route in plan.routes.values() for j in route) == list(range(6))


def test_retained_candidate_never_worse_than_current_state_greedy():
    calls = [Call(0,0,Point(-3,0),1),Call(1,0,Point(1,0),5)]
    anchors = [Anchor(0,BASE,10),Anchor(1,Point(2,0),0)]
    config = SolverConfig(1)
    plan = retained_plan(calls, anchors, 0, {0:[1,0]}, config, 0)
    assert plan_score(plan,config.priorities) <= plan_score(greedy(calls,anchors,0),config.priorities)
    validate_plan(plan,calls,anchors,0)


def test_zero_budget_does_not_claim_dp_optimality():
    plan = optimize([Call(0,0,BASE,0)],[Anchor(0,BASE,0)],0,SolverConfig(0))
    assert plan.status == 'FALLBACK' and not plan.primary_optimal and not plan.lexicographic_optimal


def test_milp_has_a_validated_starting_solution_after_objective_setup(monkeypatch):
    import dispatch.optimizer as module
    original = module.new_solver
    class RequireIncumbent:
        def __init__(self):
            self.h = original()
        def __getattr__(self, name):
            return getattr(self.h, name)
        def run(self):
            assert self.h.getSolution().value_valid, 'objective setup discarded the MIP start'
            return self.h.run()
    monkeypatch.setattr(module, 'new_solver', RequireIncumbent)
    calls = [Call(0,0,Point(1,0),4), Call(1,0,Point(2,0),1)]
    plan = module.optimize(calls,[Anchor(0,BASE,0)],0,SolverConfig(2))
    assert plan.primary_optimal and plan.lexicographic_optimal, plan.fallback_reason
