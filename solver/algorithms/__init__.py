"""The four dispatch algorithms. Each file holds one algorithm.

    greedy.py            1. earliest arrival, chaining onto busy vehicles
    closest_idle.py      2. closest free vehicle, oldest waiting call first
    nearest_neighbor.py  3. closest free vehicle, closest waiting call first
    hungarian.py         4. optimal batch matching of free vehicles to waiting calls
    waiting_line.py      shared base for 2-4 (central waiting line)
"""

from .closest_idle import ClosestIdle
from .greedy import Greedy
from .hungarian import Hungarian
from .nearest_neighbor import NearestNeighbor

ALGORITHMS = {
    "greedy": Greedy,
    "closest_idle": ClosestIdle,
    "nearest_neighbor": NearestNeighbor,
    "hungarian": Hungarian,
}
