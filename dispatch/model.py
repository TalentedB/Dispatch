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
        steps = max(0, min(time, self.end) - self.start)
        dx = self.destination.x - self.origin.x
        x_steps = min(abs(dx), steps)
        dy = self.destination.y - self.origin.y
        y_steps = min(abs(dy), max(0, steps - abs(dx)))
        return Point(self.origin.x + (1 if dx >= 0 else -1) * x_steps,
                     self.origin.y + (1 if dy >= 0 else -1) * y_steps)


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
    values = {"response": plan.total_response, "worst": max(worst_floor, plan.max_response),
              "travel": plan.travel, "deployments": sum(bool(r) for r in plan.routes.values())}
    return tuple(values[name] for name in priorities)


def make_plan(routes: dict[int, list[int]], calls: list[Call], anchors: list[Anchor],
              now: int, status: str) -> Plan:
    """Earliest feasible execution of fixed routes; no advance emergency dispatch."""
    lookup = {c.index: c for c in calls}
    result: dict[int, list[ScheduledJob]] = {}
    response, travel = [], 0
    for anchor in anchors:
        time, pos = max(now, anchor.available), anchor.position
        result[anchor.vehicle] = []
        for index in routes.get(anchor.vehicle, []):
            c = lookup[index]
            departure = max(time, c.time)
            distance = manhattan(pos, c.location)
            start = departure + distance
            result[anchor.vehicle].append(ScheduledJob(index, anchor.vehicle, departure,
                                                       start, start + c.duration))
            response.append(start - c.time)
            travel += distance
            time, pos = start + c.duration, c.location
        travel += manhattan(pos, BASE)
    return Plan(result, sum(response), max(response, default=0), travel, status)
