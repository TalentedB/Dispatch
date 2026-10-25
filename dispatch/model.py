"""Mutable simulation state, separate from immutable input calls and solver plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from tester.inputs import BASE, Call, Point, manhattan


class Status(str, Enum):
    IDLE = "IDLE"
    REPOSITIONING = "REPOSITIONING"
    RETURNING_TO_BASE = "RETURNING_TO_BASE"
    TRAVELING_TO_EMERGENCY = "TRAVELING_TO_EMERGENCY"
    SERVICING_EMERGENCY = "SERVICING_EMERGENCY"


@dataclass(frozen=True)
class Movement:
    vehicle: int
    start: int
    origin: Point
    destination: Point
    kind: Status
    end: int
    call: int | None = None

    def position(self, time: int) -> Point:
        """Travel x first, then y; clamp to the actual traversed segment."""
        elapsed_steps = max(0, min(time, self.end) - self.start)
        horizontal_offset = self.destination.x - self.origin.x
        horizontal_steps = min(abs(horizontal_offset), elapsed_steps)
        vertical_offset = self.destination.y - self.origin.y
        vertical_steps = min(abs(vertical_offset), max(0, elapsed_steps - abs(horizontal_offset)))
        return Point(
            self.origin.x + (1 if horizontal_offset >= 0 else -1) * horizontal_steps,
            self.origin.y + (1 if vertical_offset >= 0 else -1) * vertical_steps,
        )


@dataclass
class Emergency:
    call: Call
    assignment_status: str = "PENDING"
    vehicle: int | None = None
    start: int | None = None
    completion: int | None = None


@dataclass
class Ambulance:
    id: int
    position: Point = BASE
    destination: Point = BASE
    status: Status = Status.IDLE
    assignment: int | None = None
    queue: list[int] = field(default_factory=list)
    available: int = 0
    movement: Movement | None = None
    generation: int = 0

    @property
    def committed(self) -> bool:
        return self.assignment is not None

    def position_at(self, time: int) -> Point:
        return self.movement.position(time) if self.movement else self.position


@dataclass(frozen=True)
class Anchor:
    """Ready location (X,Y) and absolute availability; Z is remaining minutes.

    This is a scheduling coordinate, not the vehicle's physical destination
    or an extra geometric dimension to include in Manhattan distance.
    """

    vehicle: int
    position: Point
    available: int

    def remaining(self, now: int) -> int:
        return max(0, self.available - now)


@dataclass(frozen=True)
class ScheduledJob:
    call: int
    vehicle: int
    departure: int
    start: int
    completion: int


@dataclass
class Plan:
    routes: dict[int, list[ScheduledJob]]
    total_response: int
    max_response: int
    travel: int
    status: str
    objective: float | None = None
    gap: float | None = None
    seconds: float = 0.0
    primary_optimal: bool = False
    lexicographic_optimal: bool = False
    fallback_reason: str | None = None
    stage_statuses: list[str] = field(default_factory=list)
    algorithm: str = "unknown"
    incumbent_source: str | None = None
    model_build_seconds: float = 0.0
    dp_states: int = 0
    allowance_seconds: float | None = None


def plan_score(plan: Plan, priorities: tuple[str, ...], worst_floor: int = 0) -> tuple:
    objective_values = {
        "response": plan.total_response,
        "worst": max(worst_floor, plan.max_response),
        "travel": plan.travel,
        "deployments": sum(bool(route) for route in plan.routes.values()),
    }
    return tuple(objective_values[name] for name in priorities)


def make_plan(
    routes: dict[int, list[int]], calls: list[Call], anchors: list[Anchor], now: int, status: str
) -> Plan:
    """Earliest feasible execution of fixed routes; no advance emergency dispatch."""
    calls_by_id = {emergency.index: emergency for emergency in calls}
    scheduled_routes: dict[int, list[ScheduledJob]] = {}
    response_delays, total_travel = [], 0
    for anchor in anchors:
        available_time, position = max(now, anchor.available), anchor.position
        scheduled_routes[anchor.vehicle] = []
        for call_id in routes.get(anchor.vehicle, []):
            emergency = calls_by_id[call_id]
            departure_time = max(available_time, emergency.time)
            travel_time = manhattan(position, emergency.location)
            service_start = departure_time + travel_time
            scheduled_routes[anchor.vehicle].append(
                ScheduledJob(
                    call_id,
                    anchor.vehicle,
                    departure_time,
                    service_start,
                    service_start + emergency.duration,
                )
            )
            response_delays.append(service_start - emergency.time)
            total_travel += travel_time
            available_time, position = service_start + emergency.duration, emergency.location
        total_travel += manhattan(position, BASE)
    return Plan(
        scheduled_routes,
        sum(response_delays),
        max(response_delays, default=0),
        total_travel,
        status,
    )
