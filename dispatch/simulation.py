"""Event-driven simulation with locked incident commitments and interruptible resting travel."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from time import perf_counter
import heapq
import itertools
import math

from tester.inputs import BASE, Call, Point, manhattan
from .coverage import CoverageConfig, CoveragePlan, expanded_bounds, plan_coverage
from .model import Ambulance, Anchor, Emergency, Movement, Plan, ScheduledJob, Status, make_plan
from .optimizer import SolverConfig, greedy
from .planning import optimize
from .validation import validate_execution, validate_plan

OPTIMIZATION_BUDGET_FRACTION = 0.9
COVERAGE_BUDGET_FRACTION = 0.2
MAX_DECISION_BUDGET_FRACTION = 0.4
MIN_PLANNING_SECONDS = 0.01
INITIAL_MODEL_COST_RATE = 0.0001
MIN_CONSTRUCTION_ESTIMATE_SECONDS = 0.005
DP_SECONDS_PER_PARTITION = 0.00003
MIN_DP_ALLOWANCE_SECONDS = 0.05
MAX_DP_ALLOWANCE_SECONDS = 1.0
MIN_MILP_ALLOWANCE_SECONDS = 0.4
MAX_MILP_ALLOWANCE_SECONDS = 2.0
MILP_BUILD_TIME_MULTIPLIER = 3
MILP_TARGET_SEARCH_RESERVE_SECONDS = 0.2
MILP_ADMISSION_SAFETY_FACTOR = 1.4
MILP_ADMISSION_SEARCH_RESERVE_SECONDS = 0.05
MODEL_COST_SMOOTHING = 0.5


@dataclass(frozen=True)
class SimulationConfig:
    mode: str = "online"
    scheduler: str = "milp"
    solver: SolverConfig = field(default_factory=SolverConfig)
    staging: bool = True
    coverage: CoverageConfig = field(default_factory=CoverageConfig)
    start_time: int = 0
    runtime_limit: float | None = 20.0

    def __post_init__(self) -> None:
        if self.mode not in ("online", "offline") or self.scheduler not in ("milp", "greedy"):
            raise ValueError("invalid simulation mode/scheduler")
        if self.start_time < 0:
            raise ValueError("start time must be nonnegative")
        if self.runtime_limit is not None and (
            not math.isfinite(self.runtime_limit) or self.runtime_limit < 0
        ):
            raise ValueError("runtime limit must be finite and nonnegative")


@dataclass
class SimulationResult:
    output: str
    emergencies: dict[int, Emergency]
    movements: list[Movement]
    optimizations: list[Plan]
    coverage: list[CoveragePlan]
    end_time: int
    fleet_size: int
    start_time: int
    reused_plans: int = 0
    map_history: list[dict] = field(default_factory=list)
    coverage_skipped_budget: int = 0
    coverage_availability: list[dict] = field(default_factory=list)

    def metrics(self) -> dict:
        response_delays = [
            emergency.start - emergency.call.time for emergency in self.emergencies.values()
        ]
        service_minutes = sum(emergency.call.duration for emergency in self.emergencies.values())
        elapsed_fleet_minutes = max(1, self.fleet_size * (self.end_time - self.start_time))
        fallback_plans = [plan for plan in self.optimizations if plan.status == "FALLBACK"]
        return {
            "total_response": sum(response_delays),
            "average_response": (
                sum(response_delays) / len(response_delays) if response_delays else 0
            ),
            "maximum_response": max(response_delays, default=0),
            "total_travel": sum(movement.end - movement.start for movement in self.movements),
            "relocation_travel": sum(
                movement.end - movement.start
                for movement in self.movements
                if movement.kind == Status.REPOSITIONING
            ),
            "fleet_utilization": service_minutes / elapsed_fleet_minutes,
            "solver_seconds": sum(plan.seconds for plan in self.optimizations),
            "coverage_seconds": sum(plan.seconds for plan in self.coverage),
            "fallback_count": len(fallback_plans),
            "greedy_fallback_count": sum(
                plan.incumbent_source == "greedy" for plan in fallback_plans
            ),
            "retained_fallback_count": sum(
                plan.incumbent_source == "retained" for plan in fallback_plans
            ),
            "dp_plans": sum(plan.algorithm == "dp" for plan in self.optimizations),
            "incident_solves": len(self.optimizations),
            "reused_plans": self.reused_plans,
            "coverage_skipped_budget": self.coverage_skipped_budget,
        }


@dataclass
class _ComputationBudget:
    runtime_limit: float | None
    started_at: float = field(default_factory=perf_counter)
    incident_seconds: float = 0.0
    coverage_seconds: float = 0.0
    model_construction_cost_rate: float = INITIAL_MODEL_COST_RATE

    def remaining(self, budget_fraction: float, spent_seconds: float) -> float:
        if self.runtime_limit is None:
            return float("inf")
        deadline_remaining = self.runtime_limit * OPTIMIZATION_BUDGET_FRACTION - (
            perf_counter() - self.started_at
        )
        allocation_remaining = self.runtime_limit * budget_fraction - spent_seconds
        return max(0.0, min(allocation_remaining, deadline_remaining))

    def coverage_allowance(self) -> float:
        return self.remaining(COVERAGE_BUDGET_FRACTION, self.coverage_seconds)

    def incident_allowance(
        self, pending_count: int, vehicle_count: int, config: SolverConfig
    ) -> float:
        remaining_seconds = self.remaining(
            OPTIMIZATION_BUDGET_FRACTION, self.incident_seconds + self.coverage_seconds
        )
        model_size = pending_count**2 + vehicle_count * pending_count
        estimated_construction = max(
            MIN_CONSTRUCTION_ESTIMATE_SECONDS, self.model_construction_cost_rate * model_size
        )
        uses_dp = pending_count <= config.dp_limit
        if uses_dp:
            target_seconds = min(
                MAX_DP_ALLOWANCE_SECONDS,
                max(
                    MIN_DP_ALLOWANCE_SECONDS,
                    vehicle_count * 3**pending_count * DP_SECONDS_PER_PARTITION,
                ),
            )
        else:
            target_seconds = min(
                MAX_MILP_ALLOWANCE_SECONDS,
                max(
                    MIN_MILP_ALLOWANCE_SECONDS,
                    estimated_construction * MILP_BUILD_TIME_MULTIPLIER
                    + MILP_TARGET_SEARCH_RESERVE_SECONDS,
                ),
            )
        decision_allowance = (
            config.time_limit
            if math.isinf(remaining_seconds)
            else min(target_seconds, remaining_seconds * MAX_DECISION_BUDGET_FRACTION)
        )
        allowance = min(config.time_limit, decision_allowance)
        construction_cannot_fit = not uses_dp and allowance < (
            estimated_construction * MILP_ADMISSION_SAFETY_FACTOR
            + MILP_ADMISSION_SEARCH_RESERVE_SECONDS
        )
        return 0 if allowance < MIN_PLANNING_SECONDS or construction_cannot_fit else allowance

    def record_incident_plan(self, plan: Plan, pending_count: int, vehicle_count: int) -> None:
        self.incident_seconds += plan.seconds
        if plan.model_build_seconds:
            model_size = pending_count**2 + vehicle_count * pending_count
            observed_cost = plan.model_build_seconds / model_size
            self.model_construction_cost_rate = (
                1 - MODEL_COST_SMOOTHING
            ) * self.model_construction_cost_rate + MODEL_COST_SMOOTHING * observed_cost


class _EventKind(Enum):
    INITIALIZE = "initialize"
    EMERGENCY_REPORTED = "report"
    COVERAGE_DUE = "coverage"
    DISPATCH_DUE = "wake"
    VEHICLE_ARRIVED = "arrive"
    SERVICE_COMPLETED = "complete"


@dataclass(order=True, frozen=True)
class _SimulationEvent:
    time: int
    sequence: int
    kind: _EventKind = field(compare=False)
    vehicle_id: int = field(default=-1, compare=False)
    generation: int = field(default=-1, compare=False)
    payload: Call | int | None = field(default=None, compare=False)


@dataclass(frozen=True)
class _DispatchDecision:
    required: bool = False
    reoptimize: bool = False


def _format_drive_instruction(origin: Point, destination: Point) -> str | None:
    horizontal_distance = destination.x - origin.x
    vertical_distance = destination.y - origin.y
    directions = []
    if horizontal_distance:
        directions.append(
            f"{abs(horizontal_distance)} minutes {'east' if horizontal_distance > 0 else 'west'}"
        )
    if vertical_distance:
        directions.append(
            f"{abs(vertical_distance)} minutes {'north' if vertical_distance > 0 else 'south'}"
        )
    return "Drive " + " and ".join(directions) if directions else None


class _Simulation:
    def __init__(self, fleet_size: int, calls: list[Call], config: SimulationConfig) -> None:
        self.budget = _ComputationBudget(config.runtime_limit)
        if fleet_size < 1 or len({call.index for call in calls}) != len(calls):
            raise ValueError("fleet must be positive and call identifiers unique")
        if any(call.time < config.start_time or call.duration < 0 for call in calls):
            raise ValueError("calls precede simulation start or have negative duration")
        self.config = config
        self.calls = calls
        self.fleet = [
            Ambulance(vehicle_id, available=config.start_time) for vehicle_id in range(fleet_size)
        ]
        self.emergencies = (
            {} if config.mode == "online" else {call.index: Emergency(call) for call in calls}
        )
        self.records: list[tuple[int, int, int, str]] = []
        self.movements: list[Movement] = []
        self.incident_plans: list[Plan] = []
        self.coverage_plans: list[CoveragePlan] = []
        self.events: list[_SimulationEvent] = []
        self.event_sequence = itertools.count()
        self.current_time = config.start_time
        self.plan_revision = 0
        self.last_coverage_signature = None
        self.last_coverage_time = -(10**12)
        self.coverage_wakeup_time = None
        self.availability_refresh_time: int | None = None
        self.reused_plan_count = 0
        self.queued_plan_optimal = False
        self.skipped_coverage_count = 0
        self.coverage_bounds = expanded_bounds(config.coverage.bounds, BASE)
        self.map_history = [{"time": self.current_time, "bounds": self.coverage_bounds}]
        self.coverage_availability: list[dict] = []
        self.last_availability_signature = None

    def schedule_event(
        self,
        time: int,
        kind: _EventKind,
        vehicle_id: int = -1,
        generation: int = -1,
        payload: Call | int | None = None,
    ) -> None:
        heapq.heappush(
            self.events,
            _SimulationEvent(
                time, next(self.event_sequence), kind, vehicle_id, generation, payload
            ),
        )

    def record_action(self, vehicle: Ambulance, action: str) -> None:
        self.records.append((self.current_time, len(self.records), vehicle.id, action))

    def interrupt_movement(self, vehicle: Ambulance) -> None:
        if vehicle.movement:
            movement = vehicle.movement
            current_position = movement.position(self.current_time)
            self.movements.append(
                replace(movement, destination=current_position, end=self.current_time)
            )
            vehicle.position = vehicle.destination = current_position
            vehicle.movement = None
            vehicle.generation += 1

    def start_movement(
        self, vehicle: Ambulance, destination: Point, kind: Status, call_id: int | None = None
    ) -> None:
        assert not vehicle.committed or kind == Status.TRAVELING_TO_EMERGENCY
        self.interrupt_movement(vehicle)
        vehicle.generation += 1
        vehicle.destination, vehicle.status = destination, kind
        arrival_time = self.current_time + manhattan(vehicle.position, destination)
        vehicle.movement = Movement(
            vehicle.id,
            self.current_time,
            vehicle.position,
            destination,
            kind,
            arrival_time,
            call_id,
        )
        destination_name = {
            Status.TRAVELING_TO_EMERGENCY: "job",
            Status.RETURNING_TO_BASE: "base",
            Status.REPOSITIONING: "staging",
        }[kind]
        self.record_action(vehicle, "Start route to " + destination_name)
        drive_instruction = _format_drive_instruction(vehicle.position, destination)
        if drive_instruction:
            self.record_action(vehicle, drive_instruction)
        self.schedule_event(
            arrival_time, _EventKind.VEHICLE_ARRIVED, vehicle.id, vehicle.generation, call_id
        )

    def rebalance_idle_vehicles(self) -> None:
        if not self.config.staging:
            return
        idle_vehicles = [
            vehicle for vehicle in self.fleet if not vehicle.committed and not vehicle.queue
        ]
        idle_ids = {vehicle.id for vehicle in idle_vehicles}
        busy_anchors = []
        for anchor in self.availability_anchors():
            if anchor.vehicle in idle_ids:
                continue
            available, position = max(self.current_time, anchor.available), anchor.position
            for call_id in self.fleet[anchor.vehicle].queue:
                call = self.emergencies[call_id].call
                if call.time > self.current_time:
                    break  # Unreported locations cannot inform coverage, even offline.
                available = (
                    max(available, call.time) + manhattan(position, call.location) + call.duration
                )
                position = call.location
            busy_anchors.append(Anchor(anchor.vehicle, position, available))
        fleet_signature = (
            tuple(vehicle.id for vehicle in idle_vehicles),
            self.coverage_bounds,
            tuple(busy_anchors),
        )
        if fleet_signature != self.last_availability_signature:
            self.last_availability_signature = fleet_signature
            self.coverage_availability.append(
                {
                    "time": self.current_time,
                    "busyAnchors": [
                        {
                            "vehicle": anchor.vehicle,
                            "x": anchor.position.x,
                            "y": anchor.position.y,
                            "available": anchor.available,
                        }
                        for anchor in busy_anchors
                    ],
                }
            )
        if not idle_vehicles:
            self.last_coverage_signature = fleet_signature
            self.coverage_wakeup_time = None
            self.availability_refresh_time = None
            return
        availability_refresh_due = (
            bool(busy_anchors)
            and self.availability_refresh_time is not None
            and self.current_time >= self.availability_refresh_time
        )
        if fleet_signature == self.last_coverage_signature and not availability_refresh_due:
            return
        earliest_rebalance = self.last_coverage_time + self.config.coverage.cooldown
        free_fleet_changed = (
            self.last_coverage_signature is not None
            and fleet_signature[0] != self.last_coverage_signature[0]
        )
        # A dispatch or completion changes which vehicles can cover the city.
        # Cooldown only suppresses refinements while that free fleet is unchanged.
        if (
            self.current_time < earliest_rebalance
            and not availability_refresh_due
            and not free_fleet_changed
        ):
            self.schedule_coverage_refresh(earliest_rebalance)
            return
        self.last_coverage_signature, self.last_coverage_time = fleet_signature, self.current_time
        allowance = self.budget.coverage_allowance()
        if allowance < MIN_PLANNING_SECONDS:
            self.skipped_coverage_count += 1
            return
        positions = {
            vehicle.id: vehicle.position_at(self.current_time) for vehicle in idle_vehicles
        }
        current_targets = {
            vehicle.id: (
                vehicle.destination
                if vehicle.status == Status.REPOSITIONING
                else positions[vehicle.id]
            )
            for vehicle in idle_vehicles
        }
        coverage_config = replace(
            self.config.coverage,
            bounds=self.coverage_bounds,
            runtime_limit=None if math.isinf(allowance) else allowance,
        )
        plan = plan_coverage(
            positions,
            coverage_config,
            current_targets,
            busy_anchors=busy_anchors,
            now=self.current_time,
        )
        plan.time = self.current_time
        self.coverage_plans.append(plan)
        self.budget.coverage_seconds += plan.seconds
        if plan.improved:
            for vehicle in idle_vehicles:
                destination = plan.targets[vehicle.id]
                if vehicle.movement and vehicle.destination == destination:
                    continue
                if vehicle.position_at(self.current_time) != destination or vehicle.movement:
                    self.start_movement(vehicle, destination, Status.REPOSITIONING)
        if busy_anchors and self.config.coverage.time_limit > 0:
            refresh_interval = self.config.coverage.availability_interval
            next_free_time = min(
                (
                    anchor.available
                    for anchor in busy_anchors
                    if anchor.available > self.current_time
                ),
                default=self.current_time + refresh_interval,
            )
            # Check more closely near readiness, when a small Z reduction can
            # change the best target. Relocation hysteresis still applies.
            remaining = max(1, next_free_time - self.current_time)
            refresh_interval = min(refresh_interval, max(1, remaining // 2))
            self.availability_refresh_time = self.current_time + refresh_interval
            self.schedule_coverage_refresh(self.availability_refresh_time)
        else:
            self.coverage_wakeup_time = None
            self.availability_refresh_time = None

    def schedule_coverage_refresh(self, time: int) -> None:
        if self.coverage_wakeup_time is None or time < self.coverage_wakeup_time:
            self.coverage_wakeup_time = time
            self.schedule_event(time, _EventKind.COVERAGE_DUE)

    def availability_anchors(self) -> list[Anchor]:
        return [
            Anchor(
                vehicle.id,
                (
                    self.emergencies[vehicle.assignment].call.location
                    if vehicle.committed
                    else vehicle.position_at(self.current_time)
                ),
                vehicle.available if vehicle.committed else self.current_time,
            )
            for vehicle in self.fleet
        ]

    def plan_pending_work(self, pending_calls: list[Call], reoptimize: bool) -> Plan:
        anchors = self.availability_anchors()
        queues = {
            vehicle.id: [
                call_id
                for call_id in vehicle.queue
                if self.emergencies[call_id].assignment_status == "PENDING"
            ]
            for vehicle in self.fleet
        }
        queued_call_ids = [call_id for route in queues.values() for call_id in route]
        if not reoptimize and sorted(queued_call_ids) == sorted(
            call.index for call in pending_calls
        ):
            plan = make_plan(queues, pending_calls, anchors, self.current_time, "REUSED")
            validate_plan(plan, pending_calls, anchors, self.current_time)
            self.reused_plan_count += 1
            return plan
        if self.config.scheduler == "greedy":
            return greedy(pending_calls, anchors, self.current_time)
        fixed_worst_delay = max(
            (
                emergency.start - emergency.call.time
                for emergency in self.emergencies.values()
                if emergency.start is not None
            ),
            default=0,
        )
        allowance = self.budget.incident_allowance(
            len(pending_calls), len(anchors), self.config.solver
        )
        solver_config = replace(self.config.solver, time_limit=allowance)
        plan = optimize(
            pending_calls, anchors, self.current_time, solver_config, fixed_worst_delay, queues
        )
        self.budget.record_incident_plan(plan, len(pending_calls), len(anchors))
        if allowance == 0 and self.config.solver.time_limit > 0:
            plan.fallback_reason = (
                "run computation budget insufficient; validated "
                + str(plan.incumbent_source)
                + " fallback"
            )
        return plan

    def dispatch_emergency(self, vehicle: Ambulance, job: ScheduledJob) -> None:
        emergency = self.emergencies[job.call]
        emergency.assignment_status, emergency.vehicle = "COMMITTED", vehicle.id
        emergency.start, emergency.completion = job.start, job.completion
        vehicle.assignment, vehicle.available = job.call, job.completion
        vehicle.queue = vehicle.queue[1:]
        self.start_movement(
            vehicle, emergency.call.location, Status.TRAVELING_TO_EMERGENCY, job.call
        )

    def return_to_base(self, vehicle: Ambulance) -> None:
        if (
            vehicle.status != Status.RETURNING_TO_BASE
            and vehicle.position_at(self.current_time) != BASE
        ):
            self.start_movement(vehicle, BASE, Status.RETURNING_TO_BASE)
        elif vehicle.status == Status.SERVICING_EMERGENCY:
            # Even service at base needs the output format's zero-length return.
            self.start_movement(vehicle, BASE, Status.RETURNING_TO_BASE)

    def apply_plan(self, plan: Plan) -> None:
        for vehicle in self.fleet:
            route = plan.routes[vehicle.id]
            vehicle.queue = [job.call for job in route]
            if vehicle.committed:
                continue
            if route:
                first_job = route[0]
                if first_job.departure <= self.current_time:
                    self.dispatch_emergency(vehicle, first_job)
                else:
                    # Existing free travel continues until dispatch; silently
                    # stopping it would contradict the already printed route.
                    if vehicle.movement is None:
                        vehicle.status = Status.IDLE
                    self.schedule_event(
                        first_job.departure, _EventKind.DISPATCH_DUE, generation=self.plan_revision
                    )
            elif not self.config.staging:
                self.return_to_base(vehicle)
            elif vehicle.movement is None:
                vehicle.status = Status.IDLE

    def make_dispatch_decision(self, reoptimize: bool) -> None:
        self.plan_revision += 1
        pending_calls = [
            emergency.call
            for emergency in self.emergencies.values()
            if emergency.assignment_status == "PENDING"
        ]
        if pending_calls:
            plan = self.plan_pending_work(pending_calls, reoptimize)
            if plan.status != "REUSED":
                self.incident_plans.append(plan)
                self.queued_plan_optimal = plan.primary_optimal and plan.lexicographic_optimal
        else:
            plan = Plan({vehicle.id: [] for vehicle in self.fleet}, 0, 0, 0, "EMPTY")
            self.queued_plan_optimal = False
        self.apply_plan(plan)
        self.rebalance_idle_vehicles()

    def report_emergency(self, emergency: Call) -> None:
        updated_bounds = expanded_bounds(self.coverage_bounds, emergency.location)
        if updated_bounds != self.coverage_bounds:
            self.coverage_bounds = updated_bounds
            self.map_history.append({"time": self.current_time, "bounds": self.coverage_bounds})
        if self.config.mode == "online":
            self.emergencies[emergency.index] = Emergency(emergency)

    def complete_service(self, vehicle: Ambulance) -> None:
        emergency = self.emergencies[vehicle.assignment]
        assert emergency.completion == self.current_time
        emergency.assignment_status = "COMPLETED"
        self.record_action(vehicle, "Finish job")
        vehicle.assignment, vehicle.available = None, self.current_time
        # Preserve SERVICING until the dispatch decision selects chaining,
        # coverage, or a legacy base return, including jobs located at base.

    def finish_movement(self, vehicle: Ambulance, call_id: int | None) -> bool:
        movement = vehicle.movement
        assert movement is not None
        self.movements.append(movement)
        vehicle.position = vehicle.destination = movement.destination
        vehicle.movement = None
        if vehicle.status == Status.TRAVELING_TO_EMERGENCY:
            assert vehicle.assignment == call_id
            emergency = self.emergencies[call_id]
            assert emergency.start == self.current_time
            emergency.assignment_status = "SERVICING"
            self.record_action(vehicle, "Start job")
            vehicle.status = Status.SERVICING_EMERGENCY
            self.schedule_event(
                emergency.completion, _EventKind.SERVICE_COMPLETED, vehicle.id, vehicle.generation
            )
            return False
        arrival_action = (
            "Arrive at base" if vehicle.status == Status.RETURNING_TO_BASE else "Arrive at staging"
        )
        self.record_action(vehicle, arrival_action)
        vehicle.status, vehicle.available = Status.IDLE, self.current_time
        return True

    def has_interruptible_movement(self) -> bool:
        return any(vehicle.movement and not vehicle.committed for vehicle in self.fleet)

    def process_event(self, event: _SimulationEvent) -> _DispatchDecision:
        if event.kind == _EventKind.EMERGENCY_REPORTED:
            assert isinstance(event.payload, Call)
            self.report_emergency(event.payload)
            return _DispatchDecision(required=True, reoptimize=self.config.mode == "online")
        if event.kind == _EventKind.INITIALIZE:
            if not any(call.time <= self.current_time for call in self.calls):
                self.rebalance_idle_vehicles()
            return _DispatchDecision(required=True, reoptimize=True)
        if event.kind == _EventKind.COVERAGE_DUE:
            if event.time != self.coverage_wakeup_time:
                return _DispatchDecision()
            self.coverage_wakeup_time = None
            return _DispatchDecision(required=True)
        if event.kind == _EventKind.DISPATCH_DUE:
            current_revision = event.generation == self.plan_revision
            return _DispatchDecision(
                required=current_revision,
                reoptimize=current_revision and self.has_interruptible_movement(),
            )
        vehicle = self.fleet[event.vehicle_id]
        if vehicle.generation != event.generation:
            return _DispatchDecision()
        if event.kind == _EventKind.SERVICE_COMPLETED:
            reoptimize = (
                self.has_interruptible_movement()
                or not self.queued_plan_optimal
                or not vehicle.queue
            )
            self.complete_service(vehicle)
            # Queued jobs remain mutable. A time-limited incumbent's suffix
            # must not become a dispatch commitment merely through plan reuse.
            return _DispatchDecision(required=True, reoptimize=reoptimize)
        free_vehicle_arrived = self.finish_movement(vehicle, event.payload)
        return _DispatchDecision(required=free_vehicle_arrived, reoptimize=free_vehicle_arrived)

    def result(self) -> SimulationResult:
        assert len(self.emergencies) == len(self.calls)
        validate_execution(
            self.emergencies,
            self.movements,
            len(self.fleet),
            require_return_to_base=not self.config.staging,
        )
        lines = [
            f"Vehicle {vehicle_id}: {(time // 60) % 24:02d}:{time % 60:02d} {action}"
            for time, _, vehicle_id, action in sorted(self.records)
        ]
        output = "\n".join(lines)
        end_time = max(
            [
                self.config.start_time,
                *(emergency.completion for emergency in self.emergencies.values()),
                *(movement.end for movement in self.movements),
            ]
        )
        return SimulationResult(
            output=output + ("\n" if output else ""),
            emergencies=self.emergencies,
            movements=self.movements,
            optimizations=self.incident_plans,
            coverage=self.coverage_plans,
            end_time=end_time,
            fleet_size=len(self.fleet),
            start_time=self.config.start_time,
            reused_plans=self.reused_plan_count,
            map_history=self.map_history,
            coverage_skipped_budget=self.skipped_coverage_count,
            coverage_availability=self.coverage_availability,
        )

    def run(self) -> SimulationResult:
        self.schedule_event(self.current_time, _EventKind.INITIALIZE)
        for emergency in sorted(self.calls, key=lambda call: (call.time, call.index)):
            self.schedule_event(emergency.time, _EventKind.EMERGENCY_REPORTED, payload=emergency)
        while self.events:
            self.current_time = self.events[0].time
            for vehicle in self.fleet:
                vehicle.position = vehicle.position_at(self.current_time)
            dispatch_required = reoptimize = False
            while self.events and self.events[0].time == self.current_time:
                decision = self.process_event(heapq.heappop(self.events))
                dispatch_required |= decision.required
                reoptimize |= decision.reoptimize
            if dispatch_required:
                self.make_dispatch_decision(reoptimize)
        return self.result()


def simulate(
    fleet_size: int, calls: list[Call], config: SimulationConfig = SimulationConfig()
) -> SimulationResult:
    return _Simulation(fleet_size, calls, config).run()
