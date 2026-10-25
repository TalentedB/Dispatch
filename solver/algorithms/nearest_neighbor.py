"""Algorithm 3: nearest neighbor.

Like closest idle, but a vehicle that frees up takes the CLOSEST waiting
call instead of the oldest. With several free vehicles and waiting calls,
it repeatedly pairs the closest (vehicle, call) pair (ties: older call,
then lower vehicle id). Less wasted driving under load; far-away calls can
be skipped repeatedly.

Source: the nearest-neighbor policy for the dynamic traveling repairman
problem, Bertsimas & van Ryzin, "A stochastic and dynamic vehicle routing
problem in the Euclidean plane" (Operations Research, 1991).
"""

from __future__ import annotations

from ..model import dist
from .waiting_line import WaitingLineAlgorithm


class NearestNeighbor(WaitingLineAlgorithm):
    def match(self, now, free, waiting):
        pairs = []
        while free and waiting:
            v, call = min(((v, c) for v in free for c in waiting),
                          key=lambda p: (dist(p[0].position(now), p[1].location),
                                         p[1].time, p[1].index, p[0].id))
            free.remove(v)
            waiting.remove(call)
            pairs.append((v, call))
        return pairs
