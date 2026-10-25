"""Independent checks: do not trust integrality, route extraction, or simulation."""

from collections import Counter

from tester.inputs import BASE, Call, manhattan
from .model import Anchor, Emergency, Movement, Plan, Status


def require(condition: bool, message: str) -> None:
    # Validation must also run under python -O.
    if not condition:
        raise ValueError(message)


def validate_plan(plan: Plan, calls: list[Call], anchors: list[Anchor], now: int) -> None:
    calls_by_id = {emergency.index: emergency for emergency in calls}
    assignment_counts: Counter[int] = Counter()
    response_delays = []
    total_travel = 0
    require(set(plan.routes) == {anchor.vehicle for anchor in anchors}, "unknown/missing vehicle")
    for anchor in anchors:
        position, available = anchor.position, max(now, anchor.available)
        for job in plan.routes[anchor.vehicle]:
            require(job.call in calls_by_id, "unknown call")
            emergency = calls_by_id[job.call]
            require(job.vehicle == anchor.vehicle, "wrong vehicle")
            require(job.departure >= max(available, emergency.time), "early departure/overlap")
            travel_time = manhattan(position, emergency.location)
            require(job.start == job.departure + travel_time, "infeasible travel")
            require(job.completion == job.start + emergency.duration, "wrong service duration")
            assignment_counts[emergency.index] += 1
            response_delays.append(job.start - emergency.time)
            total_travel += travel_time
            available, position = job.completion, emergency.location
        total_travel += manhattan(position, BASE)
    require(
        assignment_counts == Counter(emergency.index for emergency in calls),
        "missing/duplicate call",
    )
    require(sum(response_delays) == plan.total_response, "wrong total response")
    require(max(response_delays, default=0) == plan.max_response, "wrong maximum response")
    require(total_travel == plan.travel, "wrong total travel")


def validate_execution(
    emergencies: dict[int, Emergency],
    movements: list[Movement],
    fleet_size: int,
    *,
    require_return_to_base: bool = True,
) -> None:
    """Replay exact physical segments and service intervals, independently of text."""
    incident_movements = [
        movement for movement in movements if movement.kind == Status.TRAVELING_TO_EMERGENCY
    ]
    require(
        Counter(movement.call for movement in incident_movements) == Counter(emergencies.keys()),
        "missing/duplicate dispatch",
    )
    for vehicle_id in range(fleet_size):
        segments = [movement for movement in movements if movement.vehicle == vehicle_id]
        position, last_movement_end = BASE, 0
        for movement in segments:
            require(
                movement.start >= last_movement_end and movement.end >= movement.start,
                "overlapping movement",
            )
            require(movement.origin == position, "teleportation")
            require(
                manhattan(movement.origin, movement.destination) == movement.end - movement.start,
                "impossible speed",
            )
            position, last_movement_end = movement.destination, movement.end
        if require_return_to_base:
            require(position == BASE, "vehicle did not return home")
        vehicle_emergencies = sorted(
            (emergency for emergency in emergencies.values() if emergency.vehicle == vehicle_id),
            key=lambda emergency: (emergency.start, emergency.completion, emergency.call.index),
        )
        service_intervals = []
        for emergency in vehicle_emergencies:
            require(emergency.assignment_status == "COMPLETED", "unfinished job")
            require(
                emergency.start >= emergency.call.time
                and emergency.completion == emergency.start + emergency.call.duration,
                "invalid service time",
            )
            matching_movements = [
                movement
                for movement in segments
                if movement.kind == Status.TRAVELING_TO_EMERGENCY
                and movement.call == emergency.call.index
                and movement.end == emergency.start
                and movement.destination == emergency.call.location
            ]
            require(
                bool(matching_movements)
                and any(movement.start >= emergency.call.time for movement in matching_movements),
                "early dispatch",
            )
            service_intervals.append((emergency.start, emergency.completion))
            for movement in segments:
                require(
                    not (movement.start < emergency.completion and movement.end > emergency.start),
                    "drive during service",
                )
        for (_, service_end), (service_start, _) in zip(service_intervals, service_intervals[1:]):
            require(service_start >= service_end, "overlapping service")
    require(
        all(emergency.vehicle in range(fleet_size) for emergency in emergencies.values()),
        "invalid vehicle",
    )
