"""Shared job-arc MILP with explicit model construction and result validation."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any
import math

from tester.inputs import BASE, Call, manhattan
from .model import Anchor, Plan, make_plan, plan_score
from .validation import validate_plan

OBJECTIVE_TOLERANCE = 1e-5
SELECTED_BINARY_THRESHOLD = 0.5


@dataclass(frozen=True)
class SolverConfig:
    time_limit: float = 30.0
    priorities: tuple[str, ...] = ("response", "worst", "travel", "deployments")
    seed: int = 0
    dp_limit: int = 7

    def __post_init__(self) -> None:
        if not math.isfinite(self.time_limit) or self.time_limit < 0:
            raise ValueError("time limit must be finite and nonnegative")
        if not 0 <= self.dp_limit <= 10:
            raise ValueError("DP queue limit must be between zero and ten")
        supported_objectives = {"response", "worst", "travel", "deployments"}
        if (
            not self.priorities
            or self.priorities[0] != "response"
            or len(set(self.priorities)) != len(self.priorities)
            or set(self.priorities) - supported_objectives
        ):
            raise ValueError("unique objective priorities must begin with response")


def new_solver() -> Any:
    import highspy

    solver = highspy.Highs()
    for option, value in (
        ("output_flag", False),
        ("threads", 1),
        ("random_seed", 0),
        ("mip_rel_gap", 0.0),
        ("mip_abs_gap", 0.0),
    ):
        solver.setOptionValue(option, value)
    return solver


def greedy(calls: list[Call], anchors: list[Anchor], now: int) -> Plan:
    routes = {anchor.vehicle: [] for anchor in anchors}
    vehicle_availability = {
        anchor.vehicle: (max(now, anchor.available), anchor.position) for anchor in anchors
    }
    for emergency in sorted(calls, key=lambda call: (call.time, call.index)):

        def arrival_order(vehicle_id: int) -> tuple[int, int]:
            available_time, position = vehicle_availability[vehicle_id]
            arrival_time = max(available_time, emergency.time) + manhattan(
                position, emergency.location
            )
            return arrival_time, vehicle_id

        vehicle_id = min(vehicle_availability, key=arrival_order)
        available_time, position = vehicle_availability[vehicle_id]
        completion_time = (
            max(available_time, emergency.time)
            + manhattan(position, emergency.location)
            + emergency.duration
        )
        vehicle_availability[vehicle_id] = completion_time, emergency.location
        routes[vehicle_id].append(emergency.index)
    plan = make_plan(routes, calls, anchors, now, "GREEDY")
    plan.algorithm = plan.incumbent_source = "greedy"
    validate_plan(plan, calls, anchors, now)
    return plan


class _RoutingModel:
    def __init__(
        self,
        solver: Any,
        calls: list[Call],
        anchors: list[Anchor],
        current_time: int,
        fixed_worst_delay: int,
        incumbent: Plan,
    ) -> None:
        import highspy

        self.solver = solver
        self.jobs = sorted(calls, key=lambda call: call.index)
        self.anchors = anchors
        self.current_time = current_time
        self.fixed_worst_delay = fixed_worst_delay
        self.job_count = len(calls)
        self.response_upper_bound = incumbent.total_response
        self.earliest_starts = {
            index: max(current_time, call.time) for index, call in enumerate(self.jobs)
        }
        self.latest_starts = {
            index: call.time + self.response_upper_bound for index, call in enumerate(self.jobs)
        }
        self.service_starts = {
            index: solver.addVariable(
                lb=self.earliest_starts[index],
                ub=self.latest_starts[index],
                type=highspy.HighsVarType.kInteger,
            )
            for index in range(self.job_count)
        }
        self.route_ranks = {
            index: solver.addVariable(lb=1, ub=self.job_count) for index in range(self.job_count)
        }
        self.first_jobs = {
            (anchor.vehicle, index): self._binary_variable()
            for anchor in anchors
            for index in range(self.job_count)
        }
        self.unused_vehicles = {anchor.vehicle: self._binary_variable() for anchor in anchors}
        self.successors = {
            (previous, following): self._binary_variable()
            for previous in range(self.job_count)
            for following in range(self.job_count)
            if previous != following
        }
        self.last_jobs = {index: self._binary_variable() for index in range(self.job_count)}
        self._add_route_constraints()
        travel_objective, deployment_objective = self._add_timing_constraints()
        response_objective = solver.qsum(
            self.service_starts[index] - call.time for index, call in enumerate(self.jobs)
        )
        solver.addConstr(response_objective <= self.response_upper_bound)
        self.worst_response = solver.addVariable(
            lb=fixed_worst_delay, ub=max(self.response_upper_bound, fixed_worst_delay)
        )
        for index, emergency in enumerate(self.jobs):
            solver.addConstr(self.worst_response >= self.service_starts[index] - emergency.time)
        self.objectives = {
            "response": response_objective,
            "worst": self.worst_response,
            "travel": travel_objective,
            "deployments": deployment_objective,
        }

    def _binary_variable(self) -> Any:
        import highspy

        return self.solver.addVariable(ub=1, type=highspy.HighsVarType.kInteger)

    def _add_route_constraints(self) -> None:
        solver = self.solver
        for anchor in self.anchors:
            solver.addConstr(
                solver.qsum(self.first_jobs[anchor.vehicle, job] for job in range(self.job_count))
                + self.unused_vehicles[anchor.vehicle]
                == 1
            )
        for job in range(self.job_count):
            incoming = solver.qsum(self.first_jobs[anchor.vehicle, job] for anchor in self.anchors)
            incoming += solver.qsum(
                self.successors[previous, job]
                for previous in range(self.job_count)
                if previous != job
            )
            outgoing = solver.qsum(
                self.successors[job, following]
                for following in range(self.job_count)
                if following != job
            )
            solver.addConstr(incoming == 1)
            solver.addConstr(outgoing + self.last_jobs[job] == 1)

    def _add_timing_constraints(self) -> tuple[Any, Any]:
        solver = self.solver
        travel_objective, deployment_objective = solver.expr(), solver.expr()
        for anchor in self.anchors:
            travel_objective += (
                manhattan(anchor.position, BASE) * self.unused_vehicles[anchor.vehicle]
            )
            for job_index, emergency in enumerate(self.jobs):
                selected = self.first_jobs[anchor.vehicle, job_index]
                travel_time = manhattan(anchor.position, emergency.location)
                travel_objective += travel_time * selected
                deployment_objective += selected
                earliest_start = (
                    max(self.current_time, anchor.available, emergency.time) + travel_time
                )
                activation_slack = max(0, earliest_start - self.earliest_starts[job_index])
                solver.addConstr(
                    self.service_starts[job_index]
                    >= earliest_start - activation_slack * (1 - selected)
                )
        for job_index, emergency in enumerate(self.jobs):
            travel_objective += manhattan(emergency.location, BASE) * self.last_jobs[job_index]
        for (previous_index, following_index), selected in self.successors.items():
            previous, following = self.jobs[previous_index], self.jobs[following_index]
            travel_time = manhattan(previous.location, following.location)
            travel_objective += travel_time * selected
            # Timing alone cannot eliminate cycles for colocated, zero-duration jobs.
            solver.addConstr(
                self.route_ranks[following_index]
                >= self.route_ranks[previous_index] + 1 - self.job_count * (1 - selected)
            )
            activation_slack = max(
                0,
                self.latest_starts[previous_index]
                + previous.duration
                + travel_time
                - self.earliest_starts[following_index],
            )
            solver.addConstr(
                self.service_starts[following_index]
                >= self.service_starts[previous_index]
                + previous.duration
                + travel_time
                - activation_slack * (1 - selected)
            )
            # A vehicle waits at its predecessor until the next call is reported.
            release_slack = max(
                0, following.time + travel_time - self.earliest_starts[following_index]
            )
            solver.addConstr(
                self.service_starts[following_index]
                >= following.time + travel_time - release_slack * (1 - selected)
            )
        return travel_objective, deployment_objective

    def starting_solution(self, plan: Plan) -> list[float]:
        values = [0.0] * self.solver.getNumCol()
        indices_by_call_id = {call.index: index for index, call in enumerate(self.jobs)}
        for anchor in self.anchors:
            previous_index = None
            for route_rank, job in enumerate(plan.routes[anchor.vehicle], 1):
                job_index = indices_by_call_id[job.call]
                values[self.service_starts[job_index].index] = job.start
                values[self.route_ranks[job_index].index] = route_rank
                selected = (
                    self.first_jobs[anchor.vehicle, job_index]
                    if previous_index is None
                    else self.successors[previous_index, job_index]
                )
                values[selected.index] = 1
                previous_index = job_index
            final_flag = (
                self.unused_vehicles[anchor.vehicle]
                if previous_index is None
                else self.last_jobs[previous_index]
            )
            values[final_flag.index] = 1
        values[self.worst_response.index] = max(self.fixed_worst_delay, plan.max_response)
        return values

    def extract_routes(self) -> dict[int, list[int]]:
        routes = {}
        for anchor in self.anchors:
            job_indices = []
            successors = [
                index
                for index in range(self.job_count)
                if self.solver.val(self.first_jobs[anchor.vehicle, index])
                > SELECTED_BINARY_THRESHOLD
            ]
            if self.solver.val(self.unused_vehicles[anchor.vehicle]) > SELECTED_BINARY_THRESHOLD:
                if successors:
                    raise ValueError("unused MILP vehicle has jobs")
                routes[anchor.vehicle] = []
                continue
            while True:
                if len(successors) != 1:
                    raise ValueError("invalid MILP successor count")
                job_index = successors[0]
                if job_index in job_indices:
                    raise ValueError("MILP subtour")
                job_indices.append(job_index)
                if self.solver.val(self.last_jobs[job_index]) > SELECTED_BINARY_THRESHOLD:
                    break
                successors = [
                    following
                    for following in range(self.job_count)
                    if following != job_index
                    and self.solver.val(self.successors[job_index, following])
                    > SELECTED_BINARY_THRESHOLD
                ]
            routes[anchor.vehicle] = [self.jobs[index].index for index in job_indices]
        return routes


def optimize(
    calls: list[Call],
    anchors: list[Anchor],
    now: int,
    config: SolverConfig = SolverConfig(),
    worst_floor: int = 0,
    incumbent: Plan | None = None,
) -> Plan:
    started_at = perf_counter()
    baseline = greedy(calls, anchors, now)
    if incumbent is not None:
        validate_plan(incumbent, calls, anchors, now)
        if plan_score(incumbent, config.priorities, worst_floor) <= plan_score(
            baseline, config.priorities, worst_floor
        ):
            baseline = incumbent
    if not calls:
        baseline.status = "EMPTY"
        return baseline
    stage_statuses: list[str] = []
    model_build_seconds = 0.0

    def fallback(reason: str) -> Plan:
        baseline.status = "FALLBACK"
        baseline.fallback_reason = reason
        baseline.stage_statuses = stage_statuses
        baseline.seconds = perf_counter() - started_at
        baseline.model_build_seconds = model_build_seconds
        return baseline

    if config.time_limit == 0:
        return fallback("time budget is zero; no MILP solve attempted")
    try:
        import highspy

        solver = new_solver()
        solver.setOptionValue("random_seed", config.seed)
        model_started_at = perf_counter()
        model = _RoutingModel(solver, calls, anchors, now, worst_floor, baseline)
        solution_values = model.starting_solution(baseline)
        model_build_seconds = perf_counter() - model_started_at
        best_plan = None
        primary_optimal = False
        completed_stages = 0
        primary_gap = None
        acceptable_statuses = {
            highspy.HighsModelStatus.kOptimal,
            highspy.HighsModelStatus.kTimeLimit,
            highspy.HighsModelStatus.kIterationLimit,
            highspy.HighsModelStatus.kInterrupt,
            highspy.HighsModelStatus.kSolutionLimit,
        }
        for objective_name in config.priorities:
            if config.time_limit - (perf_counter() - started_at) <= 0:
                break
            solver.setObjective(model.objectives[objective_name])
            if completed_stages:
                solver.clearSolver()
            # Objective changes discard the MIP start. Reseed every stage after
            # setting its objective, and include that setup in the time budget.
            solver.setSolution(
                len(solution_values), list(range(len(solution_values))), solution_values
            )
            remaining_seconds = config.time_limit - (perf_counter() - started_at)
            if remaining_seconds <= 0:
                break
            solver.setOptionValue("time_limit", remaining_seconds)
            solver.run()
            solver_status = solver.getModelStatus()
            stage_statuses.append(f"{objective_name}: {solver.modelStatusToString(solver_status)}")
            if solver_status not in acceptable_statuses or not solver.getSolution().value_valid:
                break
            solution_values = list(solver.getSolution().col_value)
            candidate = make_plan(model.extract_routes(), calls, anchors, now, "FEASIBLE")
            validate_plan(candidate, calls, anchors, now)
            if plan_score(candidate, config.priorities, worst_floor) > plan_score(
                baseline, config.priorities, worst_floor
            ):
                routes = {
                    vehicle_id: [job.call for job in route]
                    for vehicle_id, route in baseline.routes.items()
                }
                candidate = make_plan(routes, calls, anchors, now, "FEASIBLE")
            best_plan = candidate
            if objective_name == "response":
                primary_gap = solver.getInfo().mip_gap
                primary_optimal = solver_status == highspy.HighsModelStatus.kOptimal
                if (
                    primary_optimal
                    and abs(candidate.total_response - solver.getObjectiveValue())
                    > OBJECTIVE_TOLERANCE
                ):
                    raise ValueError("replayed objective disagrees with MILP optimum")
            if solver_status != highspy.HighsModelStatus.kOptimal:
                break
            completed_stages += 1
            solver.addConstr(model.objectives[objective_name] == round(solver.getObjectiveValue()))
        if best_plan is None:
            return fallback("; ".join(stage_statuses) or "budget exhausted building model")
        best_plan.primary_optimal = primary_optimal
        best_plan.lexicographic_optimal = completed_stages == len(config.priorities)
        best_plan.status = "OPTIMAL" if best_plan.lexicographic_optimal else "FEASIBLE"
        best_plan.objective = best_plan.total_response
        best_plan.gap = (
            primary_gap if primary_gap is not None and math.isfinite(primary_gap) else None
        )
        best_plan.seconds = perf_counter() - started_at
        best_plan.stage_statuses = stage_statuses
        best_plan.algorithm = "milp"
        best_plan.incumbent_source = baseline.incumbent_source
        best_plan.model_build_seconds = model_build_seconds
        return best_plan
    except (ImportError, RuntimeError, ValueError, AssertionError) as error:
        return fallback(f"{type(error).__name__}: {error}")
