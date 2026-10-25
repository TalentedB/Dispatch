"""Exact small-queue subset DP with nondominated time/cost labels."""
from dataclasses import replace
from time import perf_counter

from tester.inputs import BASE, manhattan
from .model import make_plan, plan_score
from .validation import validate_plan


class _WorkLimit(Exception):
    pass


def _pareto(bucket, label, dimensions):
    """Componentwise dominance is safe under waiting and max-delay objectives."""
    if any(all(old[k] <= label[k] for k in range(dimensions)) for old in bucket):
        return
    bucket[:] = [old for old in bucket
                 if not all(label[k] <= old[k] for k in range(dimensions))]
    bucket.append(label)


def dynamic_plan(calls, anchors, now, config, worst_floor, incumbent):
    started = perf_counter()
    deadline = started + config.time_limit
    jobs = sorted(calls, key=lambda c: c.index)
    n, full = len(jobs), (1 << len(jobs)) - 1
    best = incumbent
    generated = 0
    found_route = False

    def check():
        nonlocal generated
        generated += 1
        if generated > 100000 or (generated % 128 == 0 and perf_counter() >= deadline):
            raise _WorkLimit

    def fleet_insert(bucket, label):
        # Future vehicles depend only on the allocated subset. A strictly
        # larger accumulated primary cost cannot catch up for that same subset.
        if bucket and label[0] > bucket[0][0]:
            return
        if bucket and label[0] < bucket[0][0]:
            bucket.clear()
        _pareto(bucket, label, 4)

    # Fleet label: total response, worst delay, travel, deployments, routes.
    fleet = {0: [(0, worst_floor, 0, 0, ())]}
    complete = False
    try:
        for vehicle_index, anchor in enumerate(anchors):
            if perf_counter() >= deadline:
                raise _WorkLimit
            # Route label: completion, response sum, worst delay, travel, order.
            states = {}
            terminals = {0: [(0, 0, manhattan(anchor.position, BASE), ())]}
            for j, call in enumerate(jobs):
                start = max(now, anchor.available, call.time) + manhattan(anchor.position, call.location)
                states[1 << j, j] = [(start + call.duration, start-call.time,
                                      start-call.time, manhattan(anchor.position, call.location), (j,))]
            for mask in range(1, full + 1):
                final_labels = []
                for last in range(n):
                    for label in states.get((mask, last), []):
                        check()
                        end, response, worst, travel, order = label
                        candidate = (response, worst, travel+manhattan(jobs[last].location, BASE), order)
                        if final_labels and response < final_labels[0][0]:
                            final_labels.clear()
                        if not final_labels or response == final_labels[0][0]:
                            _pareto(final_labels, candidate, 3)
                        remaining = full ^ mask
                        while remaining:
                            bit = remaining & -remaining
                            remaining -= bit
                            j = bit.bit_length()-1
                            call = jobs[j]
                            distance = manhattan(jobs[last].location, call.location)
                            start = max(end, call.time) + distance
                            new = (start+call.duration, response+start-call.time,
                                   max(worst, start-call.time), travel+distance, order+(j,))
                            _pareto(states.setdefault((mask | bit, j), []), new, 4)
                terminals[mask] = final_labels
            next_fleet = {}
            for assigned, labels in fleet.items():
                remaining = full ^ assigned
                subset = remaining
                while True:
                    for label in labels:
                        for route in terminals[subset]:
                            check()
                            value = (label[0]+route[0], max(label[1], route[1]),
                                     label[2]+route[2], label[3]+bool(subset), label[4]+(route[3],))
                            fleet_insert(next_fleet.setdefault(assigned | subset, []), value)
                    if subset == 0:
                        break
                    subset = (subset-1) & remaining
            fleet = next_fleet
            if full in fleet:
                # A complete feasible plan already exists with any unprocessed
                # vehicles left unused. Keep it even if a later DP stage expires.
                for label in fleet[full]:
                    orders = label[4] + ((),) * (len(anchors)-vehicle_index-1)
                    routes = {a.vehicle: [jobs[j].index for j in order]
                              for a, order in zip(anchors, orders)}
                    candidate = make_plan(routes, calls, anchors, now, "DP_FEASIBLE")
                    if plan_score(candidate, config.priorities, worst_floor) <= plan_score(best, config.priorities, worst_floor):
                        best, found_route = candidate, True
        complete = True
    except _WorkLimit:
        pass
    validate_plan(best, calls, anchors, now)
    best = replace(best)
    if complete:
        best.status = "DP_OPTIMAL"
        best.primary_optimal = best.lexicographic_optimal = True
        best.algorithm = "dp"
        best.fallback_reason = None
    elif found_route:
        best.status, best.algorithm = "DP_FEASIBLE", "dp"
        best.primary_optimal = best.lexicographic_optimal = False
    else:
        best.status = "FALLBACK"
        best.fallback_reason = "DP allowance exhausted; validated incumbent retained"
        best.primary_optimal = best.lexicographic_optimal = False
    best.objective = best.total_response
    best.gap = None
    best.seconds = perf_counter()-started
    best.dp_states = generated
    best.stage_statuses = ["DP: exact" if complete else "DP: work/time limit"]
    return best
