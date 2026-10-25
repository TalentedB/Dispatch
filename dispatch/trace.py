"""Adapt completed simulations to the visualizer's existing uvec.trace/v1 contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tester.checker import Event, check, parse_output

from .model import Movement, Status

if TYPE_CHECKING:
    from .simulation import SimulationResult


def _movement_segment(movement: Movement) -> dict:
    origin, destination = movement.origin, movement.destination
    path = [[origin.x, origin.y]]
    if origin.x != destination.x:
        path.append([destination.x, origin.y])
    if origin.y != destination.y:
        path.append([destination.x, destination.y])
    segment = {
        "kind": {
            Status.TRAVELING_TO_EMERGENCY: "to_job",
            Status.RETURNING_TO_BASE: "to_base",
            Status.REPOSITIONING: "reposition",
        }[movement.kind],
        "start": movement.start,
        "end": movement.end,
        "path": path,
    }
    if movement.call is not None:
        segment["callId"] = movement.call
    # Interrupted movements already end at the actual physical position. Their
    # original target is intentionally absent from the traversed polyline.
    return segment


def build_trace(
    result: SimulationResult,
    scenario: str,
    algorithm: str = "strategy4",
    *,
    computation_seconds: float | None = None,
) -> dict:
    """Export exact call identities and paths, including interruptible staging.

    The checker remains independent of this adapter. Solver proof/fallback
    information stays separate from the validity of the executed schedule.
    """
    calls = [emergency.call for emergency in result.emergencies.values()]
    checked = check(result.fleet_size, calls, result.output, allow_reposition=True)
    if not checked.valid:
        raise ValueError("Cannot export an invalid schedule: " + "; ".join(checked.errors))

    vehicles = [{"id": vehicle, "segments": []} for vehicle in range(result.fleet_size)]
    for movement in result.movements:
        segments = vehicles[movement.vehicle]["segments"]
        segments.append(_movement_segment(movement))
        if movement.kind == Status.TRAVELING_TO_EMERGENCY:
            emergency = result.emergencies[movement.call]
            segments.append(
                {
                    "kind": "on_job",
                    "start": emergency.start,
                    "end": emergency.completion,
                    "path": [[emergency.call.location.x, emergency.call.location.y]],
                    "callId": emergency.call.index,
                }
            )
    for vehicle in vehicles:
        # Stable sorting preserves execution order for zero-length trips/jobs.
        vehicle["segments"].sort(key=lambda segment: segment["start"])

    metrics = {**checked.metrics.as_dict(), **result.metrics()}
    if computation_seconds is not None:
        metrics["computation_seconds"] = computation_seconds
    return {
        "schema": "uvec.trace/v1",
        "algorithm": {"id": algorithm},
        "scenario": {"id": scenario, "vehicles": result.fleet_size},
        "calls": [
            {
                "id": call.index,
                "time": call.time,
                "x": call.location.x,
                "y": call.location.y,
                "duration": call.duration,
            }
            for call in sorted(calls, key=lambda call: call.index)
        ],
        "vehicles": vehicles,
        "span": {"start": result.start_time, "end": result.end_time + 5},
        "check": {"valid": checked.valid, "errors": checked.errors},
        "metrics": metrics,
        "log": [
            {"time": event.time, "vehicle": event.vehicle, "text": line}
            for event, line in zip(_output_events(result.output), result.output.splitlines())
        ],
        "dispatch": {
            "mapHistory": result.map_history,
            "plans": [
                {
                    "algorithm": plan.algorithm,
                    "status": plan.status,
                    "primaryOptimal": plan.primary_optimal,
                    "lexicographicOptimal": plan.lexicographic_optimal,
                    "gap": plan.gap,
                    "seconds": plan.seconds,
                    "fallbackReason": plan.fallback_reason,
                }
                for plan in result.optimizations
            ],
        },
    }


def _output_events(output: str) -> list[Event]:
    errors: list[str] = []
    events = parse_output(output, errors)
    if errors:
        raise ValueError("Cannot export an invalid event log: " + "; ".join(errors))
    return events
