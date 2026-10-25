"""Algorithm 2: closest idle vehicle, first-come-first-served.

The standard ambulance dispatch rule. A call goes to the nearest free
vehicle (Manhattan distance; ties to the lowest id). If no vehicle is free,
the call waits; when a vehicle frees up, the OLDEST waiting call is served
first. Busy vehicles are never given extra jobs.

Source: Jagtenberg, Bhulai, van der Mei, "Dynamic ambulance dispatching: is
the closest-idle policy always optimal?" (Health Care Management Science, 2017).
"""

from __future__ import annotations

from ..model import dist
from .waiting_line import WaitingLineAlgorithm


class ClosestIdle(WaitingLineAlgorithm):
    def match(self, now, free, waiting):
        pairs = []
        for call in sorted(waiting, key=lambda c: (c.time, c.index)):
            if not free:
                break
            v = min(free, key=lambda v: (dist(v.position(now), call.location), v.id))
            free.remove(v)
            pairs.append((v, call))
        return pairs
