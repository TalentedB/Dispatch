"""Shared job-arc MILP with vehicle-specific sources, solved by HiGHS."""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
import math

from tester.inputs import BASE, Call, manhattan
from .model import Anchor, Plan, make_plan, plan_score
from .validation import validate_plan


@dataclass(frozen=True)
class SolverConfig:
    time_limit: float = 30.0
    priorities: tuple[str, ...] = ("response", "worst", "travel", "deployments")
    seed: int = 0
    dp_limit: int = 7

    def __post_init__(self):
        if not math.isfinite(self.time_limit) or self.time_limit < 0:
            raise ValueError("time limit must be finite and nonnegative")
        if not 0 <= self.dp_limit <= 10:
            raise ValueError("DP queue limit must be between zero and ten")
        if (not self.priorities or self.priorities[0] != "response"
                or len(set(self.priorities)) != len(self.priorities)
                or set(self.priorities) - {"response", "worst", "travel", "deployments"}):
            raise ValueError("unique objective priorities must begin with response")


def new_solver():
    import highspy
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("threads", 1)
    h.setOptionValue("random_seed", 0)
    h.setOptionValue("mip_rel_gap", 0.0)
    h.setOptionValue("mip_abs_gap", 0.0)
    return h


def greedy(calls: list[Call], anchors: list[Anchor], now: int) -> Plan:
    """Deterministic earliest-arrival baseline; queues use file order for ties."""
    routes = {a.vehicle: [] for a in anchors}
    state = {a.vehicle: (max(now, a.available), a.position) for a in anchors}
    for c in sorted(calls, key=lambda c: (c.time, c.index)):
        v = min(state, key=lambda v: (max(state[v][0], c.time)
                                     + manhattan(state[v][1], c.location), v))
        ready, pos = state[v]
        state[v] = (max(ready, c.time) + manhattan(pos, c.location) + c.duration, c.location)
        routes[v].append(c.index)
    plan = make_plan(routes, calls, anchors, now, "GREEDY")
    plan.algorithm = "greedy"
    plan.incumbent_source = "greedy"
    validate_plan(plan, calls, anchors, now)
    return plan


def optimize(calls: list[Call], anchors: list[Anchor], now: int,
             config: SolverConfig = SolverConfig(), worst_floor: int = 0,
             incumbent: Plan | None = None) -> Plan:
    """Optimize only mutable work. Busy vehicles enter at their locked completion."""
    started = perf_counter()
    baseline = greedy(calls, anchors, now)
    if incumbent is not None:
        validate_plan(incumbent, calls, anchors, now)
        if plan_score(incumbent, config.priorities, worst_floor) <= plan_score(baseline, config.priorities, worst_floor):
            baseline = incumbent
    if not calls:
        baseline.status = "EMPTY"
        return baseline
    statuses = []
    build_seconds = 0.0

    def fallback(reason: str) -> Plan:
        baseline.status = "FALLBACK"
        baseline.fallback_reason = reason
        baseline.stage_statuses = statuses
        baseline.seconds = perf_counter() - started
        baseline.model_build_seconds = build_seconds
        return baseline

    if config.time_limit == 0:
        return fallback("time budget is zero; no MILP solve attempted")
    try:
        import highspy
        h = new_solver()
        h.setOptionValue("random_seed", config.seed)
        model_started = perf_counter()
        n = len(calls)
        jobs = sorted(calls, key=lambda c: c.index)
        # A validated incumbent with total delay F bounds each delay by F.
        # Adding that cutoff preserves a primary optimum and tightens every M.
        F = baseline.total_response
        lower = {j: max(now, c.time) for j, c in enumerate(jobs)}
        upper = {j: c.time + F for j, c in enumerate(jobs)}
        s = {j: h.addVariable(lb=lower[j], ub=upper[j], type=highspy.HighsVarType.kInteger)
             for j in range(n)}
        rank = {j: h.addVariable(lb=1, ub=n) for j in range(n)}
        binary = lambda: h.addVariable(ub=1, type=highspy.HighsVarType.kInteger)
        # A job's successor and travel time do not depend on vehicle identity.
        # Share these arcs across the fleet; each source still represents the
        # actual availability/location after that vehicle's locked commitment.
        starts = {(a.vehicle, j): binary() for a in anchors for j in range(n)}
        unused = {a.vehicle: binary() for a in anchors}
        arcs = {(i, j): binary() for i in range(n) for j in range(n) if i != j}
        finishes = {i: binary() for i in range(n)}
        for a in anchors:
            h.addConstr(h.qsum(starts[a.vehicle, j] for j in range(n)) + unused[a.vehicle] == 1)
        for j in range(n):
            h.addConstr(h.qsum(starts[a.vehicle, j] for a in anchors)
                        + h.qsum(arcs[i, j] for i in range(n) if i != j) == 1)
            h.addConstr(h.qsum(arcs[j, k] for k in range(n) if k != j) + finishes[j] == 1)
        travel = h.expr()
        deployments = h.expr()
        for a in anchors:
            travel += manhattan(a.position, BASE) * unused[a.vehicle]
            for j in range(n):
                arc = starts[a.vehicle, j]
                d = manhattan(a.position, jobs[j].location)
                travel += d * arc
                deployments += arc
                earliest = max(now, a.available, jobs[j].time) + d
                M = max(0, earliest - lower[j])
                h.addConstr(s[j] >= earliest - M * (1 - arc))
        for i in range(n):
            travel += manhattan(jobs[i].location, BASE) * finishes[i]
        for (i, j), arc in arcs.items():
            d = manhattan(jobs[i].location, jobs[j].location)
            travel += d * arc
            h.addConstr(rank[j] >= rank[i] + 1 - n * (1 - arc))
            M = max(0, upper[i] + jobs[i].duration + d - lower[j])
            h.addConstr(s[j] >= s[i] + jobs[i].duration + d - M * (1 - arc))
            M_release = max(0, jobs[j].time + d - lower[j])
            h.addConstr(s[j] >= jobs[j].time + d - M_release * (1 - arc))
        response = h.qsum(s[j] - c.time for j, c in enumerate(jobs))
        h.addConstr(response <= F)
        worst = h.addVariable(lb=worst_floor, ub=max(F, worst_floor))
        for j, c in enumerate(jobs):
            h.addConstr(worst >= s[j] - c.time)
        objectives = {"response": response, "worst": worst, "travel": travel,
                      "deployments": deployments}
        # Feed the independently validated baseline as a complete MIP start.
        # Thus even a very short branch-and-cut run can retain a valid incumbent.
        values = [0.0] * h.getNumCol()
        by_id = {c.index: j for j, c in enumerate(jobs)}
        for a in anchors:
            previous = -1
            for order, job in enumerate(baseline.routes[a.vehicle], 1):
                j = by_id[job.call]
                values[s[j].index] = job.start
                values[rank[j].index] = order
                selected = starts[a.vehicle, j] if previous == -1 else arcs[previous, j]
                values[selected.index] = 1
                previous = j
            last = unused[a.vehicle] if previous == -1 else finishes[previous]
            values[last.index] = 1
        values[worst.index] = max(worst_floor, baseline.max_response)
        build_seconds = perf_counter() - model_started
        best = None
        primary_optimal = False
        completed_stages = 0
        primary_gap = None
        for name in config.priorities:
            remaining = config.time_limit - (perf_counter() - started)
            if remaining <= 0:
                break
            h.setObjective(objectives[name])
            if completed_stages:
                # Rebuild solve state after adding an objective equality. HiGHS
                # can otherwise reuse stale MIP presolve state across stages.
                h.clearSolver()
            # Setting the objective invalidates an earlier user solution in
            # HiGHS. Seed after it, including the very first objective stage.
            h.setSolution(len(values), list(range(len(values))), values)
            remaining = config.time_limit - (perf_counter() - started)
            if remaining <= 0:
                break
            h.setOptionValue("time_limit", remaining)
            h.run()
            status = h.getModelStatus()
            label = h.modelStatusToString(status)
            statuses.append(f"{name}: {label}")
            acceptable = {highspy.HighsModelStatus.kOptimal, highspy.HighsModelStatus.kTimeLimit,
                          highspy.HighsModelStatus.kIterationLimit, highspy.HighsModelStatus.kInterrupt,
                          highspy.HighsModelStatus.kSolutionLimit}
            if status not in acceptable or not h.getSolution().value_valid:
                break
            values = list(h.getSolution().col_value)
            routes = {}
            for a in anchors:
                route = []
                successors = [j for j in range(n) if h.val(starts[a.vehicle, j]) > 0.5]
                if h.val(unused[a.vehicle]) > 0.5:
                    if successors:
                        raise ValueError("unused MILP vehicle has jobs")
                    routes[a.vehicle] = []
                    continue
                while True:
                    if len(successors) != 1:
                        raise ValueError("invalid MILP successor count")
                    j = successors[0]
                    if j in route:
                        raise ValueError("MILP subtour")
                    route.append(j)
                    if h.val(finishes[j]) > 0.5:
                        break
                    successors = [k for k in range(n) if k != j and h.val(arcs[j, k]) > 0.5]
                routes[a.vehicle] = [jobs[j].index for j in route]
            candidate = make_plan(routes, calls, anchors, now, "FEASIBLE")
            validate_plan(candidate, calls, anchors, now)
            if plan_score(candidate, config.priorities, worst_floor) > plan_score(baseline, config.priorities, worst_floor):
                candidate = make_plan({v: [j.call for j in route] for v, route in baseline.routes.items()},
                                      calls, anchors, now, "FEASIBLE")
            best = candidate
            if name == "response":
                primary_gap = h.getInfo().mip_gap
                primary_optimal = status == highspy.HighsModelStatus.kOptimal
                if primary_optimal and abs(candidate.total_response - h.getObjectiveValue()) > 1e-5:
                    raise ValueError("replayed objective disagrees with MILP optimum")
            if status != highspy.HighsModelStatus.kOptimal:
                break  # never lock an unproven objective to run a lower priority
            completed_stages += 1
            value = round(h.getObjectiveValue())
            h.addConstr(objectives[name] == value)
        if best is None:
            return fallback("; ".join(statuses) or "budget exhausted building model")
        best.primary_optimal = primary_optimal
        best.lexicographic_optimal = completed_stages == len(config.priorities)
        best.status = "OPTIMAL" if best.lexicographic_optimal else "FEASIBLE"
        best.objective = best.total_response
        best.gap = primary_gap if primary_gap is not None and math.isfinite(primary_gap) else None
        best.seconds = perf_counter() - started
        best.stage_statuses = statuses
        best.algorithm = "milp"
        best.incumbent_source = baseline.incumbent_source
        best.model_build_seconds = build_seconds
        return best
    except (ImportError, RuntimeError, ValueError, AssertionError) as e:
        return fallback(f"{type(e).__name__}: {e}")
