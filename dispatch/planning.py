"""Retained feasible plans, exact small-queue DP, and larger-queue MILP."""
from dataclasses import replace
from time import perf_counter

from .dynamic import dynamic_plan
from .model import make_plan, plan_score
from .optimizer import SolverConfig, greedy, optimize as milp
from .validation import validate_plan


def retained_plan(calls, anchors, now, queues, config, worst_floor):
    baseline = greedy(calls, anchors, now)
    if not queues or not any(queues.values()):
        return baseline
    wanted = {c.index for c in calls}
    routes = {a.vehicle: [j for j in queues.get(a.vehicle, []) if j in wanted] for a in anchors}
    existing = [j for route in routes.values() for j in route]
    if len(existing) != len(set(existing)):
        return baseline
    deadline = perf_counter()+min(0.05, max(0.001, config.time_limit*0.1))
    for call in sorted((c for c in calls if c.index not in existing), key=lambda c: (c.time, c.index)):
        best = None
        # Always evaluate an append for every vehicle. Optional insertions are
        # bounded; stopping them never loses the already feasible incumbent.
        for a in anchors:
            order = routes[a.vehicle]
            slots = [len(order), *range(len(order))] if perf_counter() < deadline else [len(order)]
            for slot in slots:
                if slot != len(order) and perf_counter() >= deadline:
                    break
                candidate_routes = dict(routes)
                candidate_routes[a.vehicle] = order[:slot]+[call.index]+order[slot:]
                included = {j for route in candidate_routes.values() for j in route}
                candidate = make_plan(candidate_routes, [c for c in calls if c.index in included], anchors, now, "RETAINED")
                if best is None or plan_score(candidate, config.priorities, worst_floor) < plan_score(best, config.priorities, worst_floor):
                    best = candidate
        routes = {v: [j.call for j in route] for v, route in best.routes.items()}
    retained = make_plan(routes, calls, anchors, now, "RETAINED")
    validate_plan(retained, calls, anchors, now)
    retained.algorithm, retained.incumbent_source = "retained", "retained"
    return retained if plan_score(retained, config.priorities, worst_floor) <= plan_score(baseline, config.priorities, worst_floor) else baseline


def optimize(calls, anchors, now, config=SolverConfig(), worst_floor=0, queues=None):
    started = perf_counter()
    incumbent = retained_plan(calls, anchors, now, queues, config, worst_floor)
    remaining = max(0, config.time_limit-(perf_counter()-started))
    if remaining <= 0:
        result = replace(incumbent, status="FALLBACK", fallback_reason="planning budget exhausted; validated incumbent retained")
    elif 0 < len(calls) <= config.dp_limit:
        result = dynamic_plan(calls, anchors, now, replace(config, time_limit=remaining), worst_floor, incumbent)
    else:
        result = milp(calls, anchors, now, replace(config, time_limit=remaining), worst_floor, incumbent)
    result.seconds = perf_counter()-started
    result.allowance_seconds = config.time_limit
    if result.incumbent_source is None:
        result.incumbent_source = incumbent.incumbent_source
    return result
