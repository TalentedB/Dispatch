# UVEC 2026: Emergency Vehicle Dispatcher

Team localhost. Given a fleet of ambulances at a hospital at (0, 0) and a day of
emergency calls on a city grid, decide which vehicle answers each call and where idle
vehicles wait. Calls are only known once they come in (online dispatch). Travel is
Manhattan distance, 1 block = 1 minute.

Our final algorithm, **Strategy 4: adaptive hybrid**, combines exact DP/MILP assignment
with adaptive coverage, and has the lowest average response time of the eight
algorithms we built.

## Setup

Python 3.10+ and Node 24+.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt                  # highspy (MILP), NumPy, pytest
cd viz && npm ci                                     # visualizer
```

## Run

```bash
python -m dispatch inputs/brief_2_vehicles.txt                     # Strategy 4 (final algorithm)
python -m dispatch inputs/brief_2_vehicles.txt --no-staging        # same planner, vehicles wait at base
python3 -m solver inputs/brief_2_vehicles.txt --mode hungarian     # baselines: greedy, closest_idle, nearest_neighbor, hungarian
python3 bench.py                                                   # every solver x every input, checked and scored
python3 check.py inputs/brief_small.txt my_output.txt              # validate one output
```

Visualizer (replays the schedules on a city map, with a leaderboard):

```bash
cd viz
npm run traces   # run every solver on every input -> public/traces/
npm run dev      # http://localhost:5173  (press F for full-screen demo mode)
```

## Tests

```bash
python -m pytest -q          # 392 tests: checker, solvers, dispatch, coverage, trace export
cd viz && npm test && npm run lint && npm run build
```

`tester/checker.py` replays every output and rejects rule violations: leaving before a
call comes in, wrong drive or job times, switching jobs mid-route, unserved calls.

## Scripts

| Command | What it does |
|---|---|
| `python3 bench.py --detail` | Runs every solver in `solvers.txt` on every input; checks and scores each output |
| `python3 tools/stress.py` | Compares the baseline modes on hundreds of random scenarios |
| `python3 tools/generate_inputs.py --seeds 5` | Regenerates the random scenarios in `inputs/generated/` |
| `python -m tools.export_viz --only strategy4` | Writes visualizer traces (all solvers if `--only` is left out) |
| `python -m tools.benchmark_pathfinding` | Pathfinding comparison (deployment held fixed) |
| `python -m tools.benchmark_deployment` | Deployment comparison (pathfinding held fixed) |
| `python -m tools.benchmark_dispatch` | Detailed solver diagnostics for the hybrid |
| `python -m dispatch <input> --trace t.json` | One trace file to drop onto the visualizer |

## Algorithms

| Algorithm | Idea |
|---|---|
| Closest idle, FCFS | Nearest free vehicle; calls queue until one frees up |
| Greedy earliest arrival | Vehicle that can arrive soonest, including busy ones |
| Nearest neighbour | Closest free vehicle; a freed vehicle takes the closest waiting call |
| Hungarian matching | Free vehicles and waiting calls matched to minimise total distance |
| Abdullah: adaptive posts | Earliest arrival using (x, y, minutes until free); idle vehicles spread to posts |
| Hybrid DP/MILP | Exact DP for small queues, MILP (HiGHS) for larger ones; waits at base |
| **Strategy 4: adaptive hybrid** | Hybrid DP/MILP plus adaptive coverage that repositions idle vehicles |

## Structure

| Path | What it is |
|---|---|
| `dispatch/` | Strategy 4: event-driven simulation, DP/MILP planner, adaptive coverage |
| `fleet/` | Abdullah's adaptive-posts algorithm |
| `solver/` | Baseline algorithms (`solver/algorithms/`, one file each) |
| `tester/`, `bench.py`, `check.py` | Input parsing, output checker, benchmark runner |
| `tools/` | Input generator, trace exporter, benchmark scripts |
| `inputs/` | Brief examples (with expected outputs), edge cases, 26 generated scenarios |
| `viz/` | React visualizer (top-down city, 3D, timeline, leaderboard) |
| `tests/` | pytest suite |
| `docs/` | [Architecture and model](docs/ARCHITECTURE.md), [detailed benchmarks](docs/BENCHMARKS.md) |

## Results

All 30 test scenarios (944 calls), from the traces in `viz/public/traces/`, as shown in
the visualizer's leaderboard. Response = minutes from a call coming in to an ambulance
arriving. Every schedule passed the checker.

| Algorithm | Mean response (min) | Worst response (min) | Scenarios won |
|---|---|---|---|
| **Strategy 4: adaptive hybrid** | **78.4** | 648 | **21** |
| Hybrid DP/MILP, base deployment | 79.3 | **638** | 7 |
| Abdullah: adaptive posts | 81.0 | 665 | 8 |
| Nearest neighbour | 88.2 | 712 | 7 |
| Hungarian matching | 88.4 | 712 | 7 |
| Greedy earliest arrival | 127.3 | 729 | 3 |
| Dispatch greedy, base deployment | 133.6 | 729 | 3 |
| Closest idle, FCFS | 229.7 | 1247 | 3 |

Ties count as a win for each algorithm involved.

We also isolated the two halves of the problem on 29 tests
(`python -m tools.benchmark_pathfinding`, `python -m tools.benchmark_deployment`):

| Pathfinding (deployment fixed) | Mean (min) | | Deployment (pathfinding fixed) | Mean (min) |
|---|---|---|---|---|
| Manhattan | 113.4 | | Origin + static rest | 76.4 |
| Manhattan + Z (minutes until free) | 75.6 | | Dynamic + static rest | 72.8 |
| Manhattan + Z + MILP | **72.6** | | Dynamic + dynamic rest | **72.8** |

## Conclusions: what worked

- **Strategy 4 is the best overall:** it has the lowest mean response and wins 21 of 30
  scenarios.
- **Accounting for busy vehicles matters most:** the Z term, minutes until a vehicle
  is free, cuts mean response by a third.
- **MILP adds a further gain:** batching several waiting calls into one optimal plan
  brings it down a few more percent. It costs about 73 ms per call, which is fast
  enough for real time.
- **Spreading vehicles out beats waiting at the hospital,** by about 5%.
- **Continuous rebalancing roughly matches a single spread on average,** and helps the
  worst case and larger fleets.
- **What didn't help much:** reacting only to free vehicles. Closest idle is 3x worse
  than the best, because it ignores a busy vehicle that is about to finish nearby.
- **Overloaded scenarios still end up with long waits.** With 2 vehicles and 40 calls,
  no strategy can avoid queues; the fix there is more vehicles.

## Third-party code

[HiGHS/highspy](https://highs.dev/) (MIT) for MILP, NumPy (BSD-3), pytest (MIT).
Visualizer packages are listed in [viz/README.md](viz/README.md#third-party-code).
