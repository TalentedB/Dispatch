"""Independent checks: do not trust integrality, route extraction, or simulation."""
from collections import Counter

from tester.inputs import BASE, Call, manhattan
from .model import Anchor, Emergency, Movement, Plan, Status


def require(condition: bool, message: str) -> None:
    # Validation must also run under python -O.
    if not condition:
        raise ValueError(message)


def validate_plan(plan: Plan, calls: list[Call], anchors: list[Anchor], now: int) -> None:
    lookup = {c.index: c for c in calls}
    seen: Counter = Counter()
    response = []
    travel = 0
    require(set(plan.routes) == {a.vehicle for a in anchors}, "unknown/missing vehicle")
    for a in anchors:
        pos, available = a.position, max(now, a.available)
        for job in plan.routes[a.vehicle]:
            require(job.call in lookup, "unknown call")
            c = lookup[job.call]
            require(job.vehicle == a.vehicle, "wrong vehicle")
            require(job.departure >= max(available, c.time), "early departure/overlap")
            distance = manhattan(pos, c.location)
            require(job.start == job.departure + distance, "infeasible travel")
            require(job.completion == job.start + c.duration, "wrong service duration")
            seen[c.index] += 1
            response.append(job.start - c.time)
            travel += distance
            available, pos = job.completion, c.location
        travel += manhattan(pos, BASE)
    require(seen == Counter(c.index for c in calls), "missing/duplicate call")
    require(sum(response) == plan.total_response, "wrong total response")
    require(max(response, default=0) == plan.max_response, "wrong maximum response")
    require(travel == plan.travel, "wrong total travel")


def validate_execution(emergencies: dict[int, Emergency], movements: list[Movement],
                       fleet_size: int) -> None:
    """Replay exact physical segments and service intervals, independently of text."""
    incidents = [m for m in movements if m.kind == Status.TRAVELING_TO_EMERGENCY]
    require(Counter(m.call for m in incidents) == Counter(emergencies.keys()), "missing/duplicate dispatch")
    for v in range(fleet_size):
        segments = [m for m in movements if m.vehicle == v]
        pos, last = BASE, 0
        for m in segments:
            require(m.start >= last and m.end >= m.start, "overlapping movement")
            require(m.origin == pos, "teleportation")
            require(manhattan(m.origin, m.destination) == m.end - m.start, "impossible speed")
            pos, last = m.destination, m.end
        require(pos == BASE, "vehicle did not return home")
        jobs = sorted((e for e in emergencies.values() if e.vehicle == v),
                      key=lambda e: (e.start, e.completion, e.call.index))
        intervals = []
        for e in jobs:
            require(e.assignment_status == "COMPLETED", "unfinished job")
            require(e.start >= e.call.time and e.completion == e.start + e.call.duration,
                    "invalid service time")
            incident = [m for m in segments if m.kind == Status.TRAVELING_TO_EMERGENCY
                        and m.call == e.call.index and m.end == e.start and m.destination == e.call.location]
            require(bool(incident) and any(m.start >= e.call.time for m in incident), "early dispatch")
            intervals.append((e.start, e.completion))
            for m in segments:
                require(not (m.start < e.completion and m.end > e.start), "drive during service")
        for (_, end), (start, _) in zip(intervals, intervals[1:]):
            require(start >= end, "overlapping service")
    require(all(e.vehicle in range(fleet_size) for e in emergencies.values()), "invalid vehicle")
