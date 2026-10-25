"""Adaptive resting positions scored with Manhattan coverage and relocation cost."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations_with_replacement
from math import comb, isfinite, isqrt
from time import perf_counter
from typing import NamedTuple, Sequence

import numpy as np

from tester.inputs import Point, manhattan
from .model import Anchor

Bounds = tuple[int, int, int, int]
COVERAGE_COMPARISON_TOLERANCE = 1e-7
LOWER_BOUND_SAMPLE_SIZE = 32


@dataclass(frozen=True)
class CoverageConfig:
    bounds: Bounds = (-5, 5, -5, 5)
    objective: str = "center"
    relocation_weight: float = 0.1
    deployment_weight: float = 0.05
    min_improvement: float = 0.5
    cooldown: int = 10
    time_limit: float = 15.0  # Legacy option: zero disables coverage planning.
    max_candidates: int = 225
    max_demand_points: int = 10000
    max_passes: int = 4
    enumeration_limit: int = 2000
    runtime_limit: float | None = None
    availability_interval: int = 10

    def __post_init__(self) -> None:
        min_x, max_x, min_y, max_y = self.bounds
        if min_x > max_x or min_y > max_y or self.objective not in ("center", "median"):
            raise ValueError("invalid coverage boundaries/objective")
        costs_and_limits = (
            self.relocation_weight,
            self.deployment_weight,
            self.min_improvement,
            self.cooldown,
            self.time_limit,
            self.availability_interval,
        )
        if any(not isfinite(value) or value < 0 for value in costs_and_limits):
            raise ValueError("coverage costs and limits must be finite and nonnegative")
        if (
            min(self.max_candidates, self.max_demand_points, self.max_passes) < 1
            or self.enumeration_limit < 0
            or self.availability_interval < 1
        ):
            raise ValueError("invalid coverage work limits")
        if self.runtime_limit is not None and (
            not isfinite(self.runtime_limit) or self.runtime_limit < 0
        ):
            raise ValueError("invalid coverage runtime limit")

    def points(self) -> list[Point]:
        min_x, max_x, min_y, max_y = self.bounds
        return [Point(x, y) for x in range(min_x, max_x + 1) for y in range(min_y, max_y + 1)]


@dataclass
class CoveragePlan:
    targets: dict[int, Point]
    radius: int
    average: float
    relocation: int
    status: str
    seconds: float = 0.0
    gap: float | None = None  # Report compatibility; grid search has no MILP gap.
    improved: bool = False
    bounds: Bounds | None = None
    time: int | None = None
    area_shares: dict[int, float] = field(default_factory=dict)
    sampled: bool = False
    demand_points: int = 0
    candidate_count: int = 0
    busy_anchors: list[Anchor] = field(default_factory=list)


class _CoverageScore(NamedTuple):
    objective_cost: float
    relocation_travel: int
    target_coordinates: tuple[tuple[int, int], ...]
    worst_travel: int
    average_travel: float

    @property
    def comparison_key(self) -> tuple:
        return self.objective_cost, self.relocation_travel, self.target_coordinates


def expanded_bounds(bounds: Bounds, point: Point) -> Bounds:
    """Grow a square centered on base; its side length is twice the known radius."""
    known_radius = max(abs(boundary) for boundary in bounds)
    radius = max(known_radius, abs(point.x), abs(point.y))
    return -radius, radius, -radius, radius


def coverage_metrics(points: list[Point], sites: list[Point]) -> tuple[int, float]:
    nearest_distances = [min(manhattan(point, site) for site in sites) for point in points]
    return max(nearest_distances, default=0), sum(nearest_distances) / len(points)


def _sample_axis(
    origin: int, length: int, sample_count: int, weighted_blocks: bool
) -> list[tuple[int, int]]:
    """Use weighted block midpoints for demand, or boundary-inclusive candidate sites."""
    if weighted_blocks:
        return [
            (
                origin
                + (index * length // sample_count + (index + 1) * length // sample_count - 1) // 2,
                (index + 1) * length // sample_count - index * length // sample_count,
            )
            for index in range(sample_count)
        ]
    return [
        (origin + index * (length - 1) // max(1, sample_count - 1), 1)
        for index in range(sample_count)
    ]


def _build_grid(
    bounds: Bounds, point_limit: int, *, weighted_blocks: bool = False
) -> tuple[list[Point], np.ndarray]:
    min_x, max_x, min_y, max_y = bounds
    width, height = max_x - min_x + 1, max_y - min_y + 1
    x_samples = min(width, max(1, isqrt(max(1, point_limit * width // height))))
    y_samples = min(height, max(1, point_limit // x_samples))
    x_samples = min(width, max(1, point_limit // y_samples))
    grid = [
        (Point(x, y), x_weight * y_weight)
        for x, x_weight in _sample_axis(min_x, width, x_samples, weighted_blocks)
        for y, y_weight in _sample_axis(min_y, height, y_samples, weighted_blocks)
    ]
    return [point for point, _ in grid], np.array([weight for _, weight in grid], dtype=float)


def _match_vehicles_to_targets(
    vehicle_ids: list[int],
    positions: dict[int, Point],
    targets: Sequence[Point],
    config: CoverageConfig,
) -> list[Point]:
    """Find a minimum-cost matching with the Hungarian augmenting-path algorithm."""
    vehicle_count = len(vehicle_ids)
    relocation_costs = [
        [
            config.relocation_weight * manhattan(positions[vehicle_id], target)
            + config.deployment_weight * (positions[vehicle_id] != target)
            for target in targets
        ]
        for vehicle_id in vehicle_ids
    ]
    if config.relocation_weight == config.deployment_weight == 0:
        relocation_costs = [
            [manhattan(positions[vehicle_id], target) for target in targets]
            for vehicle_id in vehicle_ids
        ]

    vehicle_potentials = [0.0] * (vehicle_count + 1)
    target_potentials = [0.0] * (vehicle_count + 1)
    matched_vehicle = [0] * (vehicle_count + 1)
    previous_target = [0] * (vehicle_count + 1)
    # Index zero is the augmenting path's virtual starting target.
    for vehicle_number in range(1, vehicle_count + 1):
        matched_vehicle[0] = vehicle_number
        current_target = 0
        minimum_slack = [float("inf")] * (vehicle_count + 1)
        visited_targets = [False] * (vehicle_count + 1)
        while True:
            visited_targets[current_target] = True
            current_vehicle = matched_vehicle[current_target]
            potential_adjustment, next_target = float("inf"), 0
            for target_number in range(1, vehicle_count + 1):
                if visited_targets[target_number]:
                    continue
                reduced_cost = (
                    relocation_costs[current_vehicle - 1][target_number - 1]
                    - vehicle_potentials[current_vehicle]
                    - target_potentials[target_number]
                )
                if reduced_cost < minimum_slack[target_number]:
                    minimum_slack[target_number] = reduced_cost
                    previous_target[target_number] = current_target
                if minimum_slack[target_number] < potential_adjustment:
                    potential_adjustment, next_target = minimum_slack[target_number], target_number
            for target_number in range(vehicle_count + 1):
                if visited_targets[target_number]:
                    vehicle_potentials[matched_vehicle[target_number]] += potential_adjustment
                    target_potentials[target_number] -= potential_adjustment
                else:
                    minimum_slack[target_number] -= potential_adjustment
            current_target = next_target
            if matched_vehicle[current_target] == 0:
                break
        while current_target:
            predecessor = previous_target[current_target]
            matched_vehicle[current_target] = matched_vehicle[predecessor]
            current_target = predecessor

    assigned_targets = [targets[0]] * vehicle_count
    for target_number in range(1, vehicle_count + 1):
        assigned_targets[matched_vehicle[target_number] - 1] = targets[target_number - 1]
    return assigned_targets


class _CoverageSearch:
    def __init__(
        self,
        positions: dict[int, Point],
        config: CoverageConfig,
        existing_targets: dict[int, Point] | None,
        started_at: float,
        busy_anchors: list[Anchor],
        now: int,
    ) -> None:
        self.config = config
        self.positions = positions
        self.started_at = started_at
        self.vehicle_ids = sorted(positions)
        self.current_targets = [
            existing_targets[vehicle_id] if existing_targets else positions[vehicle_id]
            for vehicle_id in self.vehicle_ids
        ]
        self.demand_points, self.demand_weights = _build_grid(
            config.bounds, config.max_demand_points, weighted_blocks=True
        )
        candidates, _ = _build_grid(config.bounds, config.max_candidates)
        min_x, max_x, min_y, max_y = config.bounds
        clipped_targets = [
            Point(max(min_x, min(max_x, point.x)), max(min_y, min(max_y, point.y)))
            for point in self.current_targets
        ]
        center = Point((min_x + max_x) // 2, (min_y + max_y) // 2)
        self.candidate_targets = sorted(
            set(candidates + clipped_targets + [center]), key=lambda point: (point.x, point.y)
        )
        self.demand_coordinates = np.array(
            [(point.x, point.y) for point in self.demand_points], dtype=np.int64
        )
        self.distance_cache: dict[Point, np.ndarray] = {}
        self.candidate_distances = self.distances(self.candidate_targets)
        self.busy_anchors = busy_anchors
        self.busy_response_times = (
            self.distances([anchor.position for anchor in busy_anchors])
            + np.array([anchor.remaining(now) for anchor in busy_anchors])[:, None]
            if busy_anchors
            else np.empty((0, len(self.demand_points)))
        )
        self.nearest_busy_response = (
            self.busy_response_times.min(axis=0)
            if busy_anchors
            else np.full(len(self.demand_points), np.inf)
        )

    def nearest_response_times(self, targets: list[Point]) -> np.ndarray:
        return np.minimum(self.distances(targets).min(axis=0), self.nearest_busy_response)

    def deadline_expired(self) -> bool:
        return (
            self.config.runtime_limit is not None
            and perf_counter() - self.started_at >= self.config.runtime_limit
        )

    def distances(self, targets: list[Point]) -> np.ndarray:
        for target in targets:
            if target not in self.distance_cache:
                self.distance_cache[target] = np.abs(
                    self.demand_coordinates[:, 0] - target.x
                ) + np.abs(self.demand_coordinates[:, 1] - target.y)
        return np.stack([self.distance_cache[target] for target in targets])

    def score(self, targets: list[Point]) -> _CoverageScore:
        nearest_distances = self.nearest_response_times(targets)
        worst_travel = int(nearest_distances.max())
        average_travel = float(
            np.sum(nearest_distances * self.demand_weights) / self.demand_weights.sum()
        )
        relocation_travel = sum(
            manhattan(self.positions[vehicle_id], target)
            for vehicle_id, target in zip(self.vehicle_ids, targets)
        )
        moved_vehicles = sum(
            self.positions[vehicle_id] != target
            for vehicle_id, target in zip(self.vehicle_ids, targets)
        )
        coverage_cost = worst_travel if self.config.objective == "center" else average_travel
        objective_cost = (
            coverage_cost
            + self.config.relocation_weight * relocation_travel
            + self.config.deployment_weight * moved_vehicles
        )
        return _CoverageScore(
            objective_cost,
            relocation_travel,
            tuple((point.x, point.y) for point in targets),
            worst_travel,
            average_travel,
        )

    def match_targets(self, targets: Sequence[Point]) -> list[Point]:
        return _match_vehicles_to_targets(self.vehicle_ids, self.positions, targets, self.config)

    def dispersed_targets(self) -> list[Point]:
        min_x, max_x, min_y, max_y = self.config.bounds
        targets = [Point((min_x + max_x) // 2, (min_y + max_y) // 2)]
        for _ in range(1, len(self.vehicle_ids)):
            nearest_distances = self.nearest_response_times(targets)
            farthest_point = self.demand_points[int(np.argmax(nearest_distances))]
            targets.append(
                min(
                    self.candidate_targets,
                    key=lambda point: (manhattan(point, farthest_point), point.x, point.y),
                )
            )
        return self.match_targets(targets)

    def balanced_targets(self) -> list[Point]:
        min_x, max_x, min_y, max_y = self.config.bounds
        width, height = max_x - min_x + 1, max_y - min_y + 1
        partitions = []
        for row_count in range(1, min(len(self.vehicle_ids), height) + 1):
            targets = []
            for row in range(row_count):
                column_count = len(self.vehicle_ids) // row_count + (
                    row < len(self.vehicle_ids) % row_count
                )
                bottom = min_y + row * height // row_count
                top = min_y + (row + 1) * height // row_count - 1
                for column in range(column_count):
                    left = min_x + column * width // column_count
                    right = min_x + (column + 1) * width // column_count - 1
                    targets.append(
                        Point(max(min_x, min(max_x, (left + right) // 2)), (bottom + top) // 2)
                    )
            partitions.append(self.match_targets(targets))
        return min(partitions, key=lambda targets: self.score(targets).comparison_key)

    def best_replacement(
        self, targets: list[Point], vehicle_index: int, vehicle_id: int
    ) -> Point | None:
        other_targets = targets[:vehicle_index] + targets[vehicle_index + 1 :]
        nearest_other_vehicle = (
            self.distances(other_targets).min(axis=0)
            if other_targets
            else np.full(len(self.demand_points), np.iinfo(np.int64).max)
        )
        nearest_other_vehicle = np.minimum(nearest_other_vehicle, self.nearest_busy_response)
        relocation_distances = np.array(
            [manhattan(self.positions[vehicle_id], point) for point in self.candidate_targets]
        )
        movement_costs = (
            self.config.relocation_weight * relocation_distances
            + self.config.deployment_weight
            * np.array([self.positions[vehicle_id] != point for point in self.candidate_targets])
        )
        eligible_indices = np.arange(len(self.candidate_targets))
        if self.config.objective == "center":
            # A subset gives a lower bound on worst-case travel. Reject only
            # candidates that cannot even tie the current objective cost.
            sample_count = min(LOWER_BOUND_SAMPLE_SIZE, len(nearest_other_vehicle))
            hardest_points = np.argpartition(nearest_other_vehicle, -sample_count)[
                -LOWER_BOUND_SAMPLE_SIZE:
            ]
            lower_bounds = np.minimum(
                self.candidate_distances[:, hardest_points], nearest_other_vehicle[hardest_points]
            ).max(axis=1)
            current_radius = np.minimum(
                self.distances([targets[vehicle_index]])[0], nearest_other_vehicle
            ).max()
            current_cost = (
                current_radius
                + self.config.relocation_weight
                * manhattan(self.positions[vehicle_id], targets[vehicle_index])
                + self.config.deployment_weight
                * (self.positions[vehicle_id] != targets[vehicle_index])
            )
            eligible_indices = eligible_indices[
                lower_bounds + movement_costs <= current_cost + COVERAGE_COMPARISON_TOLERANCE
            ]
        if not len(eligible_indices):
            return None
        combined_distances = np.minimum(
            self.candidate_distances[eligible_indices], nearest_other_vehicle
        )
        coverage_costs = (
            combined_distances.max(axis=1)
            if self.config.objective == "center"
            else np.sum(combined_distances * self.demand_weights, axis=1)
            / self.demand_weights.sum()
        )
        objective_costs = coverage_costs + movement_costs[eligible_indices]
        preferred_order = np.lexsort(
            (eligible_indices, relocation_distances[eligible_indices], objective_costs)
        )
        return self.candidate_targets[int(eligible_indices[preferred_order[0]])]

    def improve_targets(self, targets: list[Point]) -> list[Point]:
        for _ in range(self.config.max_passes):
            changed = False
            for vehicle_index, vehicle_id in enumerate(self.vehicle_ids):
                if self.deadline_expired():
                    break
                replacement = self.best_replacement(targets, vehicle_index, vehicle_id)
                if replacement is None:
                    continue
                proposed_targets = (
                    targets[:vehicle_index] + [replacement] + targets[vehicle_index + 1 :]
                )
                if self.score(proposed_targets).comparison_key < self.score(targets).comparison_key:
                    targets, changed = proposed_targets, True
            targets = self.match_targets(targets)
            if not changed:
                break
        return targets

    def search(self, current_score: _CoverageScore) -> tuple[list[Point], _CoverageScore, str]:
        best_targets = self.current_targets
        best_score = current_score
        if self.config.time_limit == 0:
            return best_targets, best_score, "FALLBACK: coverage disabled"
        combinations = comb(
            len(self.candidate_targets) + len(self.vehicle_ids) - 1, len(self.vehicle_ids)
        )
        if combinations <= self.config.enumeration_limit:
            for placement in combinations_with_replacement(
                self.candidate_targets, len(self.vehicle_ids)
            ):
                if self.deadline_expired():
                    break
                targets = self.match_targets(placement)
                score = self.score(targets)
                if score.comparison_key < best_score.comparison_key:
                    best_targets, best_score = targets, score
            min_x, max_x, min_y, max_y = self.config.bounds
            full_grid_size = (max_x - min_x + 1) * (max_y - min_y + 1)
            status = (
                "OPTIMAL_ENUMERATION"
                if len(self.demand_points) == len(self.candidate_targets) == full_grid_size
                else "EXACT_CANDIDATES"
            )
        else:
            # Partition seeds escape plateaus where moving one clustered vehicle
            # alone cannot improve the current worst-case radius.
            starting_placements = [
                list(self.current_targets),
                self.dispersed_targets(),
                self.balanced_targets(),
            ]
            for targets in starting_placements:
                if self.deadline_expired():
                    break
                targets = self.improve_targets(targets)
                score = self.score(targets)
                if score.comparison_key < best_score.comparison_key:
                    best_targets, best_score = targets, score
            status = "HEURISTIC"
        if self.deadline_expired():
            status = "HEURISTIC_TIME_LIMIT"
        return best_targets, best_score, status

    def area_shares(self, targets: list[Point]) -> dict[int, float]:
        distances = np.vstack((self.distances(targets), self.busy_response_times))
        nearest_vehicle_ties = distances == distances.min(axis=0)
        shared_weights = (
            nearest_vehicle_ties / nearest_vehicle_ties.sum(axis=0) * self.demand_weights
        )
        percentages = np.sum(shared_weights, axis=1) / self.demand_weights.sum() * 100
        return {
            vehicle_id: float(percentage)
            for vehicle_id, percentage in zip(
                self.vehicle_ids + [anchor.vehicle for anchor in self.busy_anchors], percentages
            )
        }


def plan_coverage(
    positions: dict[int, Point],
    config: CoverageConfig = CoverageConfig(),
    existing_targets: dict[int, Point] | None = None,
    *,
    busy_anchors: list[Anchor] | None = None,
    now: int = 0,
) -> CoveragePlan:
    started_at = perf_counter()
    if not positions:
        return CoveragePlan({}, 0, 0, 0, "EMPTY", bounds=config.bounds)
    busy_anchors = busy_anchors or []
    all_vehicle_ids = list(positions) + [anchor.vehicle for anchor in busy_anchors]
    if len(set(all_vehicle_ids)) != len(all_vehicle_ids):
        raise ValueError("free vehicles and busy anchors must have distinct unique identifiers")
    search = _CoverageSearch(positions, config, existing_targets, started_at, busy_anchors, now)
    current_score = search.score(search.current_targets)
    candidate_targets, candidate_score, status = search.search(current_score)
    improved = (
        candidate_score.objective_cost
        < current_score.objective_cost - config.min_improvement - COVERAGE_COMPARISON_TOLERANCE
    )
    if (
        not improved
        and candidate_score.objective_cost
        < current_score.objective_cost - COVERAGE_COMPARISON_TOLERANCE
    ):
        status = "UNCHANGED (candidate: " + status + ")"
    chosen_targets = candidate_targets if improved else search.current_targets
    chosen_score = candidate_score if improved else current_score
    min_x, max_x, min_y, max_y = config.bounds
    full_grid_size = (max_x - min_x + 1) * (max_y - min_y + 1)
    area_shares = search.area_shares(chosen_targets)
    return CoveragePlan(
        targets=dict(zip(search.vehicle_ids, chosen_targets)),
        radius=chosen_score.worst_travel,
        average=chosen_score.average_travel,
        relocation=chosen_score.relocation_travel,
        status=status,
        seconds=perf_counter() - started_at,
        improved=improved,
        bounds=config.bounds,
        area_shares=area_shares,
        sampled=len(search.demand_points) < full_grid_size,
        demand_points=len(search.demand_points),
        candidate_count=len(search.candidate_targets),
        busy_anchors=list(busy_anchors),
    )
