"""Event-driven execution. Physical movement and accepted jobs survive replanning."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import heapq
import itertools
import math
from time import perf_counter

from tester.inputs import BASE, Call, Point, manhattan
from .coverage import CoverageConfig, CoveragePlan, expanded_bounds, plan_coverage
from .model import Ambulance, Anchor, Emergency, Movement, Plan, Status, make_plan
from .optimizer import SolverConfig, greedy
from .planning import optimize
from .validation import validate_execution, validate_plan


@dataclass(frozen=True)
class SimulationConfig:
    mode: str = "online"
    scheduler: str = "milp"
    solver: SolverConfig = field(default_factory=SolverConfig)
    staging: bool = True
    coverage: CoverageConfig = field(default_factory=CoverageConfig)
    start_time: int = 0
    runtime_limit: float | None = 20.0

    def __post_init__(self):
        if self.mode not in ("online", "offline") or self.scheduler not in ("milp", "greedy"):
            raise ValueError("invalid simulation mode/scheduler")
        if self.start_time < 0:
            raise ValueError("start time must be nonnegative")
        if self.runtime_limit is not None and (not math.isfinite(self.runtime_limit) or self.runtime_limit < 0):
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

    def metrics(self) -> dict:
        responses = [e.start - e.call.time for e in self.emergencies.values()]
        service = sum(e.call.duration for e in self.emergencies.values())
        return {
            "total_response": sum(responses),
            "average_response": sum(responses) / len(responses) if responses else 0,
            "maximum_response": max(responses, default=0),
            "total_travel": sum(m.end - m.start for m in self.movements),
            "relocation_travel": sum(m.end - m.start for m in self.movements
                                     if m.kind == Status.REPOSITIONING),
            "fleet_utilization": service / max(1, self.fleet_size * (self.end_time - self.start_time)),
            "solver_seconds": sum(p.seconds for p in self.optimizations),
            "coverage_seconds": sum(p.seconds for p in self.coverage),
            "fallback_count": sum(p.status == "FALLBACK" for p in self.optimizations),
            "greedy_fallback_count": sum(p.status == "FALLBACK" and p.incumbent_source == "greedy"
                                         for p in self.optimizations),
            "retained_fallback_count": sum(p.status == "FALLBACK" and p.incumbent_source == "retained"
                                           for p in self.optimizations),
            "dp_plans": sum(p.algorithm == "dp" for p in self.optimizations),
            "incident_solves": len(self.optimizations),
            "reused_plans": self.reused_plans,
            "coverage_skipped_budget": self.coverage_skipped_budget,
        }


def _drive(origin: Point, destination: Point) -> str | None:
    dx, dy = destination.x - origin.x, destination.y - origin.y
    parts = []
    if dx:
        parts.append(f"{abs(dx)} minutes {'east' if dx > 0 else 'west'}")
    if dy:
        parts.append(f"{abs(dy)} minutes {'north' if dy > 0 else 'south'}")
    return "Drive " + " and ".join(parts) if parts else None


def simulate(fleet_size: int, calls: list[Call], config: SimulationConfig = SimulationConfig()) -> SimulationResult:
    started = perf_counter()
    incident_spent = coverage_spent = 0.0
    model_cost_rate = 0.0001
    coverage_skipped_budget = 0

    def budget_left(fraction, spent):
        if config.runtime_limit is None:
            return float("inf")
        return max(0.0, min(config.runtime_limit*fraction-spent,
                            config.runtime_limit*0.9-(perf_counter()-started)))
    if fleet_size < 1 or len({c.index for c in calls}) != len(calls):
        raise ValueError("fleet must be positive and call identifiers unique")
    if any(c.time < config.start_time or c.duration < 0 for c in calls):
        raise ValueError("calls precede simulation start or have negative duration")
    fleet = [Ambulance(i, available=config.start_time) for i in range(fleet_size)]
    known = {} if config.mode == "online" else {c.index: Emergency(c) for c in calls}
    records, movements, optimizations, coverage_results = [], [], [], []
    heap, counter = [], itertools.count()
    now = config.start_time
    revision = 0
    stream_closed = not calls
    coverage_signature = None
    coverage_time = -10**12
    coverage_wake = None
    reused_plans = 0
    coverage_bounds = config.coverage.bounds
    map_history = [{"time": now, "bounds": coverage_bounds}]

    def event(time, kind, vehicle=-1, generation=-1, payload=None):
        heapq.heappush(heap, (time, next(counter), kind, vehicle, generation, payload))

    def emit(v, action):
        records.append((now, len(records), v.id, action))

    def stop(v):
        if v.movement:
            m = v.movement
            pos = m.position(now)
            movements.append(replace(m, destination=pos, end=now))
            v.position, v.destination, v.movement = pos, pos, None
            v.generation += 1

    def move(v, target, kind, call=None):
        assert not v.committed or kind == Status.TRAVELING_TO_EMERGENCY
        stop(v)
        v.generation += 1
        v.destination, v.status = target, kind
        end = now + manhattan(v.position, target)
        v.movement = Movement(v.id, now, v.position, target, kind, end, call)
        action = {Status.TRAVELING_TO_EMERGENCY: "job", Status.RETURNING_TO_BASE: "base",
                  Status.REPOSITIONING: "staging"}[kind]
        emit(v, "Start route to " + action)
        drive = _drive(v.position, target)
        if drive:
            emit(v, drive)
        event(end, "arrive", v.id, v.generation, call)

    def rebalance():
        nonlocal coverage_signature, coverage_time, coverage_wake, coverage_spent, coverage_skipped_budget
        if not config.staging:
            return
        # Queued incident work takes precedence over resting coverage.
        available = [v for v in fleet if not v.committed and not v.queue]
        signature = (tuple(v.id for v in available), coverage_bounds)
        if not available:
            coverage_signature = signature
            return
        if signature == coverage_signature:
            return
        if now < coverage_time + config.coverage.cooldown:
            due = coverage_time + config.coverage.cooldown
            if coverage_wake != due:
                event(due, "coverage")
                coverage_wake = due
            return
        coverage_signature, coverage_time = signature, now
        remaining = budget_left(0.2, coverage_spent)
        if remaining < 0.01:
            coverage_skipped_budget += 1
            return
        positions = {v.id: v.position_at(now) for v in available}
        targets = {v.id: v.destination if v.status == Status.REPOSITIONING else positions[v.id]
                   for v in available}
        plan = plan_coverage(positions, replace(config.coverage, bounds=coverage_bounds,
                             runtime_limit=None if math.isinf(remaining) else remaining), targets)
        plan.time = now
        coverage_results.append(plan)
        coverage_spent += plan.seconds
        if plan.improved:
            for v in available:
                target = plan.targets[v.id]
                if v.movement and v.destination == target:
                    continue
                if v.position_at(now) != target or v.movement:
                    move(v, target, Status.REPOSITIONING)

    def replan(solve):
        nonlocal revision, reused_plans, incident_spent, model_cost_rate
        revision += 1
        pending = [e.call for e in known.values() if e.assignment_status == "PENDING"]
        anchors = [Anchor(v.id,
                          known[v.assignment].call.location if v.committed else v.position_at(now),
                          v.available if v.committed else now) for v in fleet]
        if pending:
            queues = {v.id: [j for j in v.queue if known[j].assignment_status == "PENDING"]
                      for v in fleet}
            queued = [j for route in queues.values() for j in route]
            # Expected completion changes a locked anchor into a free vehicle
            # at exactly the same time/place. Its previously optimized suffix
            # remains feasible; do not solve the same routing problem again.
            if not solve and sorted(queued) == sorted(c.index for c in pending):
                plan = make_plan(queues, pending, anchors, now, "REUSED")
                validate_plan(plan, pending, anchors, now)
                reused_plans += 1
            elif config.scheduler == "milp":
                floor = max((e.start - e.call.time for e in known.values() if e.start is not None), default=0)
                remaining = budget_left(0.9, incident_spent+coverage_spent)
                size = len(pending)**2+len(anchors)*len(pending)
                construction = max(0.005, model_cost_rate*size)
                if len(pending) <= config.solver.dp_limit:
                    target = min(1.0, max(0.05, len(anchors)*3**len(pending)*0.00003))
                else:
                    target = min(2.0, max(0.4, construction*3+0.2))
                quantum = config.solver.time_limit if math.isinf(remaining) else min(target, remaining*0.4)
                limit = min(config.solver.time_limit, quantum)
                # Do not rebuild a MILP when its measured construction cost
                # would consume the entire allowance. Keep a feasible suffix.
                if limit < 0.01 or (len(pending) > config.solver.dp_limit and limit < construction*1.4+0.05):
                    limit = 0
                plan = optimize(pending, anchors, now, replace(config.solver, time_limit=limit), floor, queues)
                incident_spent += plan.seconds
                if plan.model_build_seconds:
                    model_cost_rate = 0.5*model_cost_rate+0.5*plan.model_build_seconds/size
                if limit == 0 and config.solver.time_limit > 0:
                    plan.fallback_reason = "run computation budget insufficient; validated " + str(plan.incumbent_source) + " fallback"
            else:
                plan = greedy(pending, anchors, now)
            if plan.status != "REUSED":
                optimizations.append(plan)
        else:
            plan = Plan({v.id: [] for v in fleet}, 0, 0, 0, "EMPTY")
        for v in fleet:
            route = plan.routes[v.id]
            v.queue = [j.call for j in route]
            if v.committed:
                continue
            if route:
                first = route[0]
                if first.departure <= now:
                    e = known[first.call]
                    e.assignment_status, e.vehicle = "COMMITTED", v.id
                    e.start, e.completion = first.start, first.completion
                    v.assignment, v.available = first.call, first.completion
                    v.queue = v.queue[1:]
                    move(v, e.call.location, Status.TRAVELING_TO_EMERGENCY, first.call)
                else:
                    # A stationary vehicle waits at its predecessor. Existing
                    # return/staging travel continues until an actual dispatch;
                    # silently stopping it would contradict the printed route.
                    if v.movement is None:
                        v.status = Status.IDLE
                    event(first.departure, "wake", generation=revision)
            elif not config.staging or (stream_closed and not pending and all(not a.committed for a in fleet)):
                if v.status != Status.RETURNING_TO_BASE and v.position_at(now) != BASE:
                    move(v, BASE, Status.RETURNING_TO_BASE)
                elif v.status == Status.SERVICING_EMERGENCY:
                    # Even a job at base uses the established zero-length return.
                    move(v, BASE, Status.RETURNING_TO_BASE)
            elif v.movement is None:
                v.status = Status.IDLE
        # Incident queues always take priority over idle coverage.
        if not (stream_closed and not any(v.queue for v in fleet)
                and all(not v.committed for v in fleet)):
            rebalance()

    event(now, "initialize")
    for c in sorted(calls, key=lambda c: (c.time, c.index)):
        event(c.time, "report", payload=c)
    if calls:
        event(max(c.time for c in calls), "stream_end")
    while heap:
        now = heap[0][0]
        for v in fleet:
            v.position = v.position_at(now)
        changed = False
        solve = False
        while heap and heap[0][0] == now:
            _, _, kind, vid, generation, payload = heapq.heappop(heap)
            if kind == "report":
                # Even offline incident optimization cannot expand coverage
                # from an emergency whose report event has not happened yet.
                updated_bounds = expanded_bounds(coverage_bounds, payload.location)
                if updated_bounds != coverage_bounds:
                    coverage_bounds = updated_bounds
                    map_history.append({"time": now, "bounds": coverage_bounds})
                if config.mode == "online":
                    known[payload.index] = Emergency(payload)
                    solve = True
                changed = True
            elif kind == "stream_end":
                stream_closed, changed = True, True
            elif kind in ("initialize", "coverage"):
                changed = True
                if kind == "initialize":
                    # Staging starts physically at base, including offline runs.
                    if not any(c.time <= now for c in calls):
                        rebalance()
                    solve = True
                else:
                    coverage_wake = None
            elif kind == "wake":
                changed |= generation == revision
                # A returning/staging vehicle may have moved since planning.
                solve |= generation == revision and any(v.movement and not v.committed for v in fleet)
            elif kind in ("arrive", "complete"):
                v = fleet[vid]
                if v.generation != generation:
                    continue  # a redirected movement's obsolete event
                if kind == "complete":
                    changed = True
                    solve |= any(a.movement and not a.committed for a in fleet)
                    e = known[v.assignment]
                    assert e.completion == now
                    e.assignment_status = "COMPLETED"
                    emit(v, "Finish job")
                    v.assignment, v.available = None, now
                    # Keep the servicing status until replan chooses chaining,
                    # coverage, or the required final return (including zero drive).
                else:
                    m = v.movement
                    movements.append(m)
                    v.position, v.destination, v.movement = m.destination, m.destination, None
                    if v.status == Status.TRAVELING_TO_EMERGENCY:
                        assert v.assignment == payload
                        e = known[payload]
                        assert e.start == now
                        e.assignment_status = "SERVICING"
                        emit(v, "Start job")
                        v.status = Status.SERVICING_EMERGENCY
                        event(e.completion, "complete", v.id, v.generation)
                    else:
                        changed = True
                        solve = True  # a free vehicle's physical anchor changed
                        emit(v, "Arrive at base" if v.status == Status.RETURNING_TO_BASE else "Arrive at staging")
                        v.status, v.available = Status.IDLE, now
        if changed:
            replan(solve)
    assert len(known) == len(calls)
    validate_execution(known, movements, fleet_size)
    output = "\n".join(f"Vehicle {v}: {(t // 60) % 24:02d}:{t % 60:02d} {action}"
                       for t, _, v, action in sorted(records))
    end_time = max([config.start_time, *(e.completion for e in known.values()),
                    *(m.end for m in movements)])
    return SimulationResult(output + ("\n" if output else ""), known, movements,
                            optimizations, coverage_results, end_time, fleet_size, config.start_time,
                            reused_plans, map_history, coverage_skipped_budget)
