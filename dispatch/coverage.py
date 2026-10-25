"""Deterministic adaptive grid coverage, independent of incident scheduling."""
from __future__ import annotations
from dataclasses import dataclass, field
from itertools import combinations_with_replacement
from math import comb, isfinite, isqrt
from time import perf_counter
import numpy as np
from tester.inputs import Point, manhattan


@dataclass(frozen=True)
class CoverageConfig:
    bounds: tuple[int, int, int, int] = (0, 9, 0, 9)
    objective: str = "center"
    relocation_weight: float = 0.1
    deployment_weight: float = 0.05
    min_improvement: float = 0.5
    cooldown: int = 10
    time_limit: float = 15.0  # Compatibility: zero disables planning; no solver deadline.
    max_candidates: int = 225
    max_demand_points: int = 10000
    max_passes: int = 4
    enumeration_limit: int = 2000
    runtime_limit: float | None = None

    def __post_init__(self):
        xmin, xmax, ymin, ymax = self.bounds
        if xmin > xmax or ymin > ymax or self.objective not in ("center", "median"):
            raise ValueError("invalid coverage boundaries/objective")
        if any(not isfinite(x) or x < 0 for x in
               (self.relocation_weight, self.deployment_weight, self.min_improvement,
                self.cooldown, self.time_limit)):
            raise ValueError("coverage costs and limits must be finite and nonnegative")
        if min(self.max_candidates, self.max_demand_points, self.max_passes) < 1 or self.enumeration_limit < 0:
            raise ValueError("invalid coverage work limits")
        if self.runtime_limit is not None and (not isfinite(self.runtime_limit) or self.runtime_limit < 0):
            raise ValueError("invalid coverage runtime limit")

    def points(self) -> list[Point]:
        xmin, xmax, ymin, ymax = self.bounds
        return [Point(x, y) for x in range(xmin, xmax + 1) for y in range(ymin, ymax + 1)]


@dataclass
class CoveragePlan:
    targets: dict[int, Point]
    radius: int
    average: float
    relocation: int
    status: str
    seconds: float = 0.0
    gap: float | None = None  # Compatibility; no MILP gap for grid planning.
    improved: bool = False
    bounds: tuple[int, int, int, int] | None = None
    time: int | None = None
    area_shares: dict[int, float] = field(default_factory=dict)
    sampled: bool = False
    demand_points: int = 0
    candidate_count: int = 0


def expanded_bounds(bounds, point: Point):
    xmin, xmax, ymin, ymax = bounds
    return min(xmin, point.x), max(xmax, point.x), min(ymin, point.y), max(ymax, point.y)


def coverage_metrics(points: list[Point], sites: list[Point]) -> tuple[int, float]:
    distances = [min(manhattan(p, s) for s in sites) for p in points]
    return max(distances, default=0), sum(distances) / len(points)


def _grid(bounds, limit, *, demand=False):
    """Full small grids; weighted representative blocks for very large maps."""
    xmin, xmax, ymin, ymax = bounds
    width, height = xmax-xmin+1, ymax-ymin+1
    nx = min(width, max(1, isqrt(max(1, limit*width//height))))
    ny = min(height, max(1, limit//nx))
    nx = min(width, max(1, limit//ny))
    def axis(lo, size, count):
        if demand:
            return [(lo+(i*size//count+(i+1)*size//count-1)//2,
                     (i+1)*size//count-i*size//count) for i in range(count)]
        return [(lo+i*(size-1)//max(1, count-1), 1) for i in range(count)]
    grid = [(Point(x,y), wx*wy) for x,wx in axis(xmin,width,nx)
            for y,wy in axis(ymin,height,ny)]
    return [p for p,_ in grid], np.array([w for _,w in grid], dtype=float)


def _match(vehicles, positions, sites, config):
    """Hungarian minimum relocation-cost matching, O(fleet^3)."""
    n = len(vehicles)
    costs = [[config.relocation_weight*manhattan(positions[v],s)
              +config.deployment_weight*(positions[v]!=s) for s in sites] for v in vehicles]
    if config.relocation_weight == config.deployment_weight == 0:
        costs = [[manhattan(positions[v],s) for s in sites] for v in vehicles]
    u,w,matched,previous = [0.]*(n+1),[0.]*(n+1),[0]*(n+1),[0]*(n+1)
    for i in range(1,n+1):
        matched[0],j0 = i,0
        best,used = [float('inf')]*(n+1),[False]*(n+1)
        while True:
            used[j0] = True
            i0,delta,j1 = matched[j0],float('inf'),0
            for j in range(1,n+1):
                if not used[j]:
                    cost = costs[i0-1][j-1]-u[i0]-w[j]
                    if cost < best[j]:
                        best[j],previous[j] = cost,j0
                    if best[j] < delta:
                        delta,j1 = best[j],j
            for j in range(n+1):
                if used[j]:
                    u[matched[j]] += delta
                    w[j] -= delta
                else:
                    best[j] -= delta
            j0 = j1
            if matched[j0] == 0:
                break
        while j0:
            j1 = previous[j0]
            matched[j0],j0 = matched[j1],j1
    result = [None]*n
    for j in range(1,n+1):
        result[matched[j]-1] = sites[j-1]
    return result


def plan_coverage(positions: dict[int,Point], config: CoverageConfig = CoverageConfig(),
                  existing_targets: dict[int,Point] | None = None) -> CoveragePlan:
    started = perf_counter()
    def expired():
        return config.runtime_limit is not None and perf_counter()-started >= config.runtime_limit
    if not positions:
        return CoveragePlan({},0,0,0,'EMPTY',bounds=config.bounds)
    vehicles = sorted(positions)
    current = [existing_targets[v] if existing_targets else positions[v] for v in vehicles]
    demand,weights = _grid(config.bounds,config.max_demand_points,demand=True)
    candidates,_ = _grid(config.bounds,config.max_candidates)
    xmin,xmax,ymin,ymax = config.bounds
    candidates = sorted(set(candidates+[Point(max(xmin,min(xmax,p.x)),max(ymin,min(ymax,p.y))) for p in current]
                            +[Point((xmin+xmax)//2,(ymin+ymax)//2)]),key=lambda p:(p.x,p.y))
    demand_xy = np.array([(p.x,p.y) for p in demand],dtype=np.int64)
    distance_cache = {}
    def distances(sites):
        for p in sites:
            if p not in distance_cache:
                distance_cache[p] = (np.abs(demand_xy[:,0]-p.x)
                                     + np.abs(demand_xy[:,1]-p.y))
        return np.stack([distance_cache[p] for p in sites])
    candidate_distances = distances(candidates)
    def score(sites):
        nearest = distances(sites).min(axis=0)
        radius,average = int(nearest.max()),float(np.sum(nearest*weights)/weights.sum())
        travel = sum(manhattan(positions[v],p) for v,p in zip(vehicles,sites))
        cost = ((radius if config.objective=='center' else average)+config.relocation_weight*travel
                +config.deployment_weight*sum(positions[v]!=p for v,p in zip(vehicles,sites)))
        return cost,travel,tuple((p.x,p.y) for p in sites),radius,average
    old_score = score(current)
    best,best_score,status = current,old_score,'HEURISTIC'
    if config.time_limit == 0:
        status = 'FALLBACK: coverage disabled'
    elif comb(len(candidates)+len(vehicles)-1,len(vehicles)) <= config.enumeration_limit:
        for sites in combinations_with_replacement(candidates,len(vehicles)):
            if expired():
                break
            matched = _match(vehicles,positions,sites,config)
            value = score(matched)
            if value[:3] < best_score[:3]:
                best,best_score = matched,value
        status = ('OPTIMAL_ENUMERATION' if len(demand)==len(candidates)==(xmax-xmin+1)*(ymax-ymin+1)
                  else 'EXACT_CANDIDATES')
        if expired():
            status = 'HEURISTIC_TIME_LIMIT'
    else:
        # Continue existing destinations, and independently try a dispersed start.
        spread = [Point((xmin+xmax)//2,(ymin+ymax)//2)]
        for _ in range(1,len(vehicles)):
            nearest = distances(spread).min(axis=0)
            farthest = demand[int(np.argmax(nearest))]
            spread.append(min(candidates,key=lambda p:(manhattan(p,farthest),p.x,p.y)))
        # Balanced rectangular partitions escape the p-center plateaus where
        # moving either of two clustered vehicles alone cannot improve radius.
        partitions = []
        width,height = xmax-xmin+1,ymax-ymin+1
        for rows in range(1,min(len(vehicles),height)+1):
            sites = []
            for row in range(rows):
                columns = len(vehicles)//rows+(row<len(vehicles)%rows)
                lo,hi = ymin+row*height//rows,ymin+(row+1)*height//rows-1
                for column in range(columns):
                    left = xmin+column*width//columns
                    right = xmin+(column+1)*width//columns-1
                    sites.append(Point(max(xmin,min(xmax,(left+right)//2)),(lo+hi)//2))
            partitions.append(_match(vehicles,positions,sites,config))
        balanced = min(partitions,key=lambda sites:score(sites)[:3])
        for sites in [list(current),_match(vehicles,positions,spread,config),balanced]:
            if expired():
                break
            for _ in range(config.max_passes):
                changed = False
                for i,v in enumerate(vehicles):
                    if expired():
                        break
                    remaining = sites[:i]+sites[i+1:]
                    nearest = (distances(remaining).min(axis=0) if remaining else
                               np.full(len(demand),np.iinfo(np.int64).max))
                    relocation = np.array([manhattan(positions[v],p) for p in candidates])
                    movement_cost = (config.relocation_weight*relocation
                                     +config.deployment_weight*np.array([positions[v]!=p for p in candidates]))
                    eligible = np.arange(len(candidates))
                    if config.objective == 'center':
                        # A subset gives a lower bound on the full worst-case
                        # radius. Discard only candidates that cannot match the
                        # current score, preserving all improving/tied choices.
                        hard = np.argpartition(nearest,-min(32,len(nearest)))[-32:]
                        bound = np.minimum(candidate_distances[:,hard],nearest[hard]).max(axis=1)
                        current_radius = np.minimum(distances([sites[i]])[0],nearest).max()
                        current_cost = (current_radius+config.relocation_weight*manhattan(positions[v],sites[i])
                                        +config.deployment_weight*(positions[v]!=sites[i]))
                        eligible = eligible[bound+movement_cost <= current_cost+1e-7]
                    if not len(eligible):
                        continue
                    combined = np.minimum(candidate_distances[eligible],nearest)
                    coverage = (combined.max(axis=1) if config.objective=='center' else
                                np.sum(combined*weights,axis=1)/weights.sum())
                    costs = coverage+movement_cost[eligible]
                    order = np.lexsort((eligible,relocation[eligible],costs))
                    candidate = candidates[int(eligible[order[0]])]
                    proposal = sites[:i]+[candidate]+sites[i+1:]
                    if score(proposal)[:3] < score(sites)[:3]:
                        sites,changed = proposal,True
                sites = _match(vehicles,positions,sites,config)
                if not changed:
                    break
            value = score(sites)
            if value[:3] < best_score[:3]:
                best,best_score = sites,value
        if expired():
            status = 'HEURISTIC_TIME_LIMIT'
    improved = best_score[0] < old_score[0]-config.min_improvement-1e-7
    if not improved and best_score[0] < old_score[0]-1e-7:
        status = 'UNCHANGED (candidate: '+status+')'
    chosen = best if improved else current
    value = best_score if improved else old_score
    matrix = distances(chosen)
    ties = matrix==matrix.min(axis=0)
    shares = np.sum((ties/ties.sum(axis=0))*weights,axis=1)/weights.sum()*100
    return CoveragePlan(dict(zip(vehicles,chosen)),value[3],value[4],value[1],status,
                        seconds=perf_counter()-started,improved=improved,bounds=config.bounds,
                        area_shares={v:float(s) for v,s in zip(vehicles,shares)},
                        sampled=len(demand)<(xmax-xmin+1)*(ymax-ymin+1),
                        demand_points=len(demand),candidate_count=len(candidates))
