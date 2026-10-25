"""Algorithm 4: Hungarian batch matching.

Each time a call arrives or a vehicle frees up, ALL free vehicles and
waiting calls are matched at once so the total Manhattan distance is as
small as possible (the assignment problem, solved with the Kuhn-Munkres /
Hungarian algorithm). If there are more calls than free vehicles, the
leftover calls keep waiting.

Source: batch matching as used in ride-hailing dispatch (collect requests
and free drivers, solve the assignment to minimise total pickup distance).
"""

from __future__ import annotations

from ..model import dist
from .waiting_line import WaitingLineAlgorithm


class Hungarian(WaitingLineAlgorithm):
    """Minimum-total-distance assignment of free vehicles to waiting calls.

    If there are more waiting calls than free vehicles, the assignment picks
    which calls get served now to minimise total distance; the rest keep
    waiting. Ties are broken toward older calls and lower vehicle ids.
    """

    def match(self, now, free, waiting):
        waiting = sorted(waiting, key=lambda c: (c.time, c.index))
        # Scale distances so tie-break terms (call age rank, vehicle id) never outweigh a real minute.
        scale = (len(waiting) + 1) * (len(free) + 1)
        cost = [[dist(v.position(now), c.location) * scale + j * (len(free) + 1) + i
                 for j, c in enumerate(waiting)] for i, v in enumerate(free)]
        assignment = hungarian(cost)
        return [(free[i], waiting[j]) for i, j in assignment]


def hungarian(cost: list[list[int]]) -> list[tuple[int, int]]:
    """Minimum-cost assignment for a rectangular matrix (Kuhn-Munkres, O(n^2 m)).

    Returns (row, col) pairs; every row is matched if rows <= cols, otherwise
    every column is. Standard potentials-based implementation.
    """
    rows, cols = len(cost), len(cost[0]) if cost else 0
    if rows == 0 or cols == 0:
        return []
    transposed = rows > cols
    if transposed:
        cost = [list(col) for col in zip(*cost)]
        rows, cols = cols, rows

    INF = float("inf")
    u = [0] * (rows + 1)  # row potentials
    v = [0] * (cols + 1)  # column potentials
    p = [0] * (cols + 1)  # p[j] = row matched to column j (1-based, 0 = none)
    way = [0] * (cols + 1)
    for i in range(1, rows + 1):
        p[0] = i
        j0 = 0
        minv = [INF] * (cols + 1)
        used = [False] * (cols + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, cols + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(cols + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    pairs = [(p[j] - 1, j - 1) for j in range(1, cols + 1) if p[j]]
    return sorted((c, r) if transposed else (r, c) for r, c in pairs)
