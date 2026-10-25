"""Algorithm 1: earliest-arrival greedy.

Each new call goes to the vehicle that can reach it soonest, counting every
vehicle: idle ones leave now, ones heading home turn around from where they
are, busy ones chain it after their queued work. Ties go to the lowest id.
A job never moves once queued.

This is "closest unit" dispatch extended to busy units, and is what the
brief's examples show.
"""

from __future__ import annotations

from ..engine import Vehicle
from ..model import Call, dist


def arrival_if_appended(v: Vehicle, now: int, call: Call) -> int:
    t, pos = v.available(now)
    for queued in v.queue:
        t += dist(pos, queued.location) + queued.duration
        pos = queued.location
    return t + dist(pos, call.location)


class Greedy:
    def on_call(self, now: int, call: Call, vehicles: list[Vehicle]) -> None:
        best = min(vehicles, key=lambda v: (arrival_if_appended(v, now, call), v.id))
        best.queue.append(call)

    def on_free(self, now: int, vehicles: list[Vehicle]) -> None:
        pass
