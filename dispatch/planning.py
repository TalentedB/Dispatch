"""Choose a validated starting plan, then optimize with subset DP or MILP."""

from dataclasses import replace
from time import perf_counter

from tester.inputs import Call
from .dynamic import dynamic_plan
from .model import Anchor, Plan, make_plan, plan_score
from .optimizer import SolverConfig, greedy, optimize as optimize_milp
from .validation import validate_plan

MAX_INSERTION_SECONDS = 0.05
MIN_INSERTION_SECONDS = 0.001
INSERTION_BUDGET_FRACTION = 0.1


def _insert_reported_call(
    emergency: Call,
    routes: dict[int, list[int]],
    calls: list[Call],
    anchors: list[Anchor],
    current_time: int,
    config: SolverConfig,
    fixed_worst_delay: int,
    insertion_deadline: float,
) -> Plan:
    best_plan = None
    for anchor in anchors:
        current_order = routes[anchor.vehicle]
        append_position = len(current_order)
        insertion_positions = [append_position]
        if perf_counter() < insertion_deadline:
            insertion_positions.extend(range(append_position))
        for insertion_position in insertion_positions:
            if insertion_position != append_position and perf_counter() >= insertion_deadline:
                break
            candidate_routes = dict(routes)
            candidate_routes[anchor.vehicle] = (
                current_order[:insertion_position]
                + [emergency.index]
                + current_order[insertion_position:]
            )
            included_call_ids = {
                call_id for route in candidate_routes.values() for call_id in route
            }
            included_calls = [call for call in calls if call.index in included_call_ids]
            candidate = make_plan(
                candidate_routes, included_calls, anchors, current_time, "RETAINED"
            )
            if best_plan is None or plan_score(
                candidate, config.priorities, fixed_worst_delay
            ) < plan_score(best_plan, config.priorities, fixed_worst_delay):
                best_plan = candidate
    # Every vehicle's append position is evaluated even after the deadline.
    assert best_plan is not None
    return best_plan


def retained_plan(
    calls: list[Call],
    anchors: list[Anchor],
    now: int,
    queues: dict[int, list[int]] | None,
    config: SolverConfig,
    worst_floor: int,
) -> Plan:
    greedy_plan = greedy(calls, anchors, now)
    if not queues or not any(queues.values()):
        return greedy_plan

    pending_call_ids = {call.index for call in calls}
    retained_routes = {
        anchor.vehicle: [
            call_id for call_id in queues.get(anchor.vehicle, []) if call_id in pending_call_ids
        ]
        for anchor in anchors
    }
    retained_call_ids = [call_id for route in retained_routes.values() for call_id in route]
    if len(retained_call_ids) != len(set(retained_call_ids)):
        return greedy_plan

    insertion_allowance = min(
        MAX_INSERTION_SECONDS,
        max(MIN_INSERTION_SECONDS, config.time_limit * INSERTION_BUDGET_FRACTION),
    )
    insertion_deadline = perf_counter() + insertion_allowance
    new_calls = sorted(
        (call for call in calls if call.index not in retained_call_ids),
        key=lambda call: (call.time, call.index),
    )
    for emergency in new_calls:
        extended_plan = _insert_reported_call(
            emergency,
            retained_routes,
            calls,
            anchors,
            now,
            config,
            worst_floor,
            insertion_deadline,
        )
        retained_routes = {
            vehicle_id: [job.call for job in route]
            for vehicle_id, route in extended_plan.routes.items()
        }

    candidate = make_plan(retained_routes, calls, anchors, now, "RETAINED")
    validate_plan(candidate, calls, anchors, now)
    candidate.algorithm = candidate.incumbent_source = "retained"
    if plan_score(candidate, config.priorities, worst_floor) <= plan_score(
        greedy_plan, config.priorities, worst_floor
    ):
        return candidate
    return greedy_plan


def optimize(
    calls: list[Call],
    anchors: list[Anchor],
    now: int,
    config: SolverConfig = SolverConfig(),
    worst_floor: int = 0,
    queues: dict[int, list[int]] | None = None,
) -> Plan:
    started_at = perf_counter()
    incumbent = retained_plan(calls, anchors, now, queues, config, worst_floor)
    remaining_seconds = max(0, config.time_limit - (perf_counter() - started_at))
    search_config = replace(config, time_limit=remaining_seconds)

    if remaining_seconds <= 0:
        result = replace(
            incumbent,
            status="FALLBACK",
            fallback_reason="planning budget exhausted; validated incumbent retained",
        )
    elif 0 < len(calls) <= config.dp_limit:
        result = dynamic_plan(calls, anchors, now, search_config, worst_floor, incumbent)
    else:
        result = optimize_milp(calls, anchors, now, search_config, worst_floor, incumbent)

    result.seconds = perf_counter() - started_at
    result.allowance_seconds = config.time_limit
    if result.incumbent_source is None:
        result.incumbent_source = incumbent.incumbent_source
    return result
