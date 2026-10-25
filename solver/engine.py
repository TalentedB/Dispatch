"""Event-driven simulation shared by every approach.

The engine owns the rules; a Algorithm only decides what sits in each
vehicle's queue. Each vehicle has:

  * current  - the job it is driving to or working on. Locked: the algorithm
               can never touch it ("can't switch once travelling").
  * queue    - jobs planned for it but not started yet. The algorithm may
               add, reorder, or move these between vehicles at any event.

A algorithm may also keep calls in its own `waiting` list (a central queue)
and hand them to vehicles later, e.g. when one frees up.

Events are processed minute by minute in this order:
  1. vehicles whose job finishes now become free
  2. calls arriving now are handed to the algorithm, one at a time, in order
  3. if a vehicle became free, the algorithm may re-plan (on_free)
  4. every free vehicle with a non-empty queue departs for its first job;
     a free vehicle with nothing queued that just finished heads home

So a vehicle that finishes exactly when a call arrives can chain straight to
it, and a vehicle heading home can be redirected from wherever it is.
The algorithm only ever sees calls that have already arrived.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from .model import BASE, Call, Point, dist, position_along


@dataclass(frozen=True)
class Trip:
    call: Call
    depart_time: int
    depart_pos: Point
    arrive_time: int
    finish_time: int


@dataclass
class Return:
    start_time: int
    start_pos: Point
    interrupted_at: int | None = None  # set if the vehicle leaves again before/at reaching base


class Vehicle:
    def __init__(self, vid: int):
        self.id = vid
        self.current: Trip | None = None
        self.queue: list[Call] = []
        self.history: list[Trip | Return] = []
        # Where it's heading home from, when not on a job. At start it sits at base.
        self.home_from: Point = BASE
        self.home_since: int = 0

    def position(self, now: int) -> Point:
        """Where the vehicle is at `now` (only meaningful when it has no current job)."""
        return position_along(self.home_from, BASE, now - self.home_since)

    def available(self, now: int) -> tuple[int, Point]:
        """When and where it could start driving to its next queued job."""
        if self.current:
            return self.current.finish_time, self.current.call.location
        return now, self.position(now)


class Algorithm(Protocol):
    def on_call(self, now: int, call: Call, vehicles: list[Vehicle]) -> None:
        """Put `call` into some vehicle's queue (and optionally re-plan other queued jobs)."""

    def on_free(self, now: int, vehicles: list[Vehicle]) -> None:
        """A vehicle just finished a job; optionally re-plan queued jobs."""


def _queued(vehicles: list[Vehicle], algorithm) -> Counter:
    """Every call the algorithm is responsible for: in a vehicle queue or in its waiting list."""
    waiting = getattr(algorithm, "waiting", [])
    return Counter(c.index for v in vehicles for c in v.queue) + Counter(c.index for c in waiting)


def run(num_vehicles: int, calls: list[Call], algorithm: Algorithm) -> list[Vehicle]:
    vehicles = [Vehicle(i) for i in range(num_vehicles)]
    pending_calls = sorted(calls, key=lambda c: (c.time, c.index))
    next_call = 0

    while True:
        busy_until = [v.current.finish_time for v in vehicles if v.current]
        candidates = busy_until + ([pending_calls[next_call].time] if next_call < len(pending_calls) else [])
        if not candidates:
            break
        now = min(candidates)

        # 1. Finish jobs.
        freed = []
        for v in vehicles:
            if v.current and v.current.finish_time == now:
                v.home_from, v.home_since = v.current.call.location, now
                v.current = None
                freed.append(v)

        # 2. New calls.
        while next_call < len(pending_calls) and pending_calls[next_call].time == now:
            call = pending_calls[next_call]
            next_call += 1
            before = _queued(vehicles, algorithm)
            algorithm.on_call(now, call, vehicles)
            before[call.index] += 1
            if _queued(vehicles, algorithm) != before:
                raise RuntimeError(f"algorithm lost or duplicated jobs while handling call #{call.index}")

        # 3. Re-plan when capacity frees up.
        if freed:
            before = _queued(vehicles, algorithm)
            algorithm.on_free(now, vehicles)
            if _queued(vehicles, algorithm) != before:
                raise RuntimeError("algorithm lost or duplicated jobs in on_free")

        # 4. Dispatch.
        for v in vehicles:
            if v.current:
                continue
            last = v.history[-1] if v.history else None
            if v.queue:
                call = v.queue.pop(0)
                start = v.position(now)
                if isinstance(last, Return) and last.interrupted_at is None:
                    last.interrupted_at = now
                arrive = now + dist(start, call.location)
                v.current = Trip(call, now, start, arrive, arrive + call.duration)
                v.history.append(v.current)
            elif v in freed:
                v.history.append(Return(now, v.home_from))

    if getattr(algorithm, "waiting", []):
        raise RuntimeError("algorithm left calls waiting with every vehicle free")
    return vehicles
