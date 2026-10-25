"""Exact subset scheduling with named, nondominated partial schedules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from time import perf_counter
from typing import NamedTuple, TypeVar

from tester.inputs import BASE, Call, manhattan
from .model import Anchor, Plan, make_plan, plan_score
from .optimizer import SolverConfig
from .validation import validate_plan

MAX_EVALUATED_LABELS = 100_000
DEADLINE_CHECK_INTERVAL = 128


class _RoutePrefix(NamedTuple):
    completion_time: int
    total_response: int
    maximum_response: int
    travel_time: int
    job_order: tuple[int, ...]

    @property
    def costs(self) -> tuple[int, ...]:
        return self.completion_time, self.total_response, self.maximum_response, self.travel_time


class _VehicleRoute(NamedTuple):
    total_response: int
    maximum_response: int
    travel_time: int
    job_order: tuple[int, ...]

    @property
    def costs(self) -> tuple[int, ...]:
        return self.total_response, self.maximum_response, self.travel_time


class _FleetAssignment(NamedTuple):
    total_response: int
    maximum_response: int
    travel_time: int
    deployed_vehicles: int
    vehicle_routes: tuple[tuple[int, ...], ...]

    @property
    def costs(self) -> tuple[int, ...]:
        return self.total_response, self.maximum_response, self.travel_time, self.deployed_vehicles


_Label = TypeVar("_Label", _RoutePrefix, _VehicleRoute, _FleetAssignment)
_VehicleRoutes = dict[int, list[_VehicleRoute]]
_FleetAssignments = dict[int, list[_FleetAssignment]]


class _SearchLimitReached(Exception):
    pass


@dataclass
class _SearchBudget:
    deadline: float
    evaluated_labels: int = 0

    def check_deadline(self) -> None:
        if perf_counter() >= self.deadline:
            raise _SearchLimitReached

    def count_label(self) -> None:
        self.evaluated_labels += 1
        if self.evaluated_labels > MAX_EVALUATED_LABELS:
            raise _SearchLimitReached
        if self.evaluated_labels % DEADLINE_CHECK_INTERVAL == 0:
            self.check_deadline()


def _keep_nondominated(frontier: list[_Label], candidate: _Label) -> None:
    """Preserve completion/response/travel tradeoffs instead of choosing one winner."""
    candidate_costs = candidate.costs
    if any(
        all(previous <= proposed for previous, proposed in zip(label.costs, candidate_costs))
        for label in frontier
    ):
        return
    frontier[:] = [
        label
        for label in frontier
        if not all(proposed <= previous for proposed, previous in zip(candidate_costs, label.costs))
    ]
    frontier.append(candidate)


def _keep_best_fleet_assignment(
    frontier: list[_FleetAssignment], candidate: _FleetAssignment
) -> None:
    # Remaining vehicles see the same unassigned jobs. Higher accumulated
    # response cannot recover; equal response may still trade worst delay/travel.
    if frontier and candidate.total_response > frontier[0].total_response:
        return
    if frontier and candidate.total_response < frontier[0].total_response:
        frontier.clear()
    _keep_nondominated(frontier, candidate)


def _build_vehicle_routes(
    jobs: list[Call],
    anchor: Anchor,
    current_time: int,
    all_jobs_mask: int,
    budget: _SearchBudget,
) -> _VehicleRoutes:
    prefixes: dict[tuple[int, int], list[_RoutePrefix]] = {}
    completed_routes = {0: [_VehicleRoute(0, 0, manhattan(anchor.position, BASE), ())]}
    for job_index, emergency in enumerate(jobs):
        travel_time = manhattan(anchor.position, emergency.location)
        service_start = max(current_time, anchor.available, emergency.time) + travel_time
        response_delay = service_start - emergency.time
        prefixes[1 << job_index, job_index] = [
            _RoutePrefix(
                service_start + emergency.duration,
                response_delay,
                response_delay,
                travel_time,
                (job_index,),
            )
        ]

    for served_jobs_mask in range(1, all_jobs_mask + 1):
        terminal_frontier: list[_VehicleRoute] = []
        for last_job_index, last_emergency in enumerate(jobs):
            for prefix in prefixes.get((served_jobs_mask, last_job_index), []):
                budget.count_label()
                terminal = _VehicleRoute(
                    prefix.total_response,
                    prefix.maximum_response,
                    prefix.travel_time + manhattan(last_emergency.location, BASE),
                    prefix.job_order,
                )
                if (
                    terminal_frontier
                    and terminal.total_response < terminal_frontier[0].total_response
                ):
                    terminal_frontier.clear()
                if (
                    not terminal_frontier
                    or terminal.total_response == terminal_frontier[0].total_response
                ):
                    _keep_nondominated(terminal_frontier, terminal)

                unserved_jobs_mask = all_jobs_mask ^ served_jobs_mask
                while unserved_jobs_mask:
                    next_job_bit = unserved_jobs_mask & -unserved_jobs_mask
                    unserved_jobs_mask -= next_job_bit
                    next_job_index = next_job_bit.bit_length() - 1
                    next_emergency = jobs[next_job_index]
                    travel_time = manhattan(last_emergency.location, next_emergency.location)
                    service_start = max(prefix.completion_time, next_emergency.time) + travel_time
                    response_delay = service_start - next_emergency.time
                    extension = _RoutePrefix(
                        service_start + next_emergency.duration,
                        prefix.total_response + response_delay,
                        max(prefix.maximum_response, response_delay),
                        prefix.travel_time + travel_time,
                        prefix.job_order + (next_job_index,),
                    )
                    destination = served_jobs_mask | next_job_bit, next_job_index
                    _keep_nondominated(prefixes.setdefault(destination, []), extension)
        completed_routes[served_jobs_mask] = terminal_frontier
    return completed_routes


def _assign_next_vehicle(
    assignments: _FleetAssignments,
    vehicle_routes: _VehicleRoutes,
    all_jobs_mask: int,
    budget: _SearchBudget,
) -> _FleetAssignments:
    next_assignments: _FleetAssignments = {}
    for assigned_jobs_mask, assignment_frontier in assignments.items():
        remaining_jobs_mask = all_jobs_mask ^ assigned_jobs_mask
        vehicle_jobs_mask = remaining_jobs_mask
        while True:
            for assignment in assignment_frontier:
                for route in vehicle_routes[vehicle_jobs_mask]:
                    budget.count_label()
                    candidate = _FleetAssignment(
                        assignment.total_response + route.total_response,
                        max(assignment.maximum_response, route.maximum_response),
                        assignment.travel_time + route.travel_time,
                        assignment.deployed_vehicles + bool(vehicle_jobs_mask),
                        assignment.vehicle_routes + (route.job_order,),
                    )
                    combined_jobs_mask = assigned_jobs_mask | vehicle_jobs_mask
                    _keep_best_fleet_assignment(
                        next_assignments.setdefault(combined_jobs_mask, []), candidate
                    )
            if vehicle_jobs_mask == 0:
                break
            vehicle_jobs_mask = (vehicle_jobs_mask - 1) & remaining_jobs_mask
    return next_assignments


def _reconstruct_plan(
    assignment: _FleetAssignment,
    jobs: list[Call],
    calls: list[Call],
    anchors: list[Anchor],
    current_time: int,
) -> Plan:
    unused_vehicle_count = len(anchors) - len(assignment.vehicle_routes)
    vehicle_orders = assignment.vehicle_routes + ((),) * unused_vehicle_count
    routes = {
        anchor.vehicle: [jobs[index].index for index in order]
        for anchor, order in zip(anchors, vehicle_orders)
    }
    return make_plan(routes, calls, anchors, current_time, "DP_FEASIBLE")


def _finish_search(
    best_plan: Plan,
    completed_search: bool,
    found_complete_route: bool,
    budget: _SearchBudget,
    started_at: float,
) -> Plan:
    result = replace(best_plan)
    if completed_search:
        result.status = "DP_OPTIMAL"
        result.primary_optimal = result.lexicographic_optimal = True
        result.algorithm = "dp"
        result.fallback_reason = None
    elif found_complete_route:
        result.status, result.algorithm = "DP_FEASIBLE", "dp"
        result.primary_optimal = result.lexicographic_optimal = False
    else:
        result.status = "FALLBACK"
        result.fallback_reason = "DP allowance exhausted; validated incumbent retained"
        result.primary_optimal = result.lexicographic_optimal = False
    result.objective = result.total_response
    result.gap = None
    result.seconds = perf_counter() - started_at
    result.dp_states = budget.evaluated_labels
    result.stage_statuses = ["DP: exact" if completed_search else "DP: work/time limit"]
    return result


def dynamic_plan(
    calls: list[Call],
    anchors: list[Anchor],
    now: int,
    config: SolverConfig,
    worst_floor: int,
    incumbent: Plan,
) -> Plan:
    started_at = perf_counter()
    budget = _SearchBudget(started_at + config.time_limit)
    jobs = sorted(calls, key=lambda emergency: emergency.index)
    all_jobs_mask = (1 << len(jobs)) - 1
    assignments = {0: [_FleetAssignment(0, worst_floor, 0, 0, ())]}
    best_plan = incumbent
    completed_search = found_complete_route = False
    try:
        for anchor in anchors:
            budget.check_deadline()
            vehicle_routes = _build_vehicle_routes(jobs, anchor, now, all_jobs_mask, budget)
            assignments = _assign_next_vehicle(assignments, vehicle_routes, all_jobs_mask, budget)
            # A complete assignment can leave later vehicles unused. Preserve
            # it before searching them, so a deadline never loses feasible work.
            for assignment in assignments.get(all_jobs_mask, []):
                candidate = _reconstruct_plan(assignment, jobs, calls, anchors, now)
                if plan_score(candidate, config.priorities, worst_floor) <= plan_score(
                    best_plan, config.priorities, worst_floor
                ):
                    best_plan, found_complete_route = candidate, True
        completed_search = True
    except _SearchLimitReached:
        pass
    validate_plan(best_plan, calls, anchors, now)
    return _finish_search(best_plan, completed_search, found_complete_route, budget, started_at)
