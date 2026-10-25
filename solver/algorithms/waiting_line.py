"""Shared base for closest_idle, nearest_neighbor and hungarian.

These follow the classic dispatch setup: a call goes to a *free* vehicle
(idle at base, or heading home - it turns around from where it is). If no
vehicle is free, the call waits in a central waiting line. Whenever a call
arrives or a vehicle frees up, waiting calls are matched to free vehicles.
Each algorithm only defines how that matching is done (`match`).

Distances are Manhattan (grid) distances from each vehicle's current position.
"""

from __future__ import annotations

from ..engine import Vehicle
from ..model import Call


class WaitingLineAlgorithm:
    def __init__(self):
        self.waiting: list[Call] = []

    def on_call(self, now: int, call: Call, vehicles: list[Vehicle]) -> None:
        self.waiting.append(call)
        self._dispatch(now, vehicles)

    def on_free(self, now: int, vehicles: list[Vehicle]) -> None:
        self._dispatch(now, vehicles)

    def _dispatch(self, now: int, vehicles: list[Vehicle]) -> None:
        free = [v for v in vehicles if v.current is None and not v.queue]
        if free and self.waiting:
            for v, call in self.match(now, free, list(self.waiting)):
                v.queue.append(call)
                self.waiting.remove(call)

    def match(self, now: int, free: list[Vehicle], waiting: list[Call]) -> list[tuple[Vehicle, Call]]:
        """Return (vehicle, call) pairs to dispatch now."""
        raise NotImplementedError
