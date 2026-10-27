# Dispatch

An emergency vehicle dispatch simulator built by Team localhost for UVEC 2026.
It decides which ambulance should answer each call and where available vehicles
should wait for the next emergency.

![Dispatch replay of 10 ambulances responding to 80 calls on a city grid](docs/assets/dispatch-demo.gif)

*A replay of the `big_fleet_2` scenario using our adaptive dispatch solver.
The map shows ambulance movements, emergency calls, and response coverage.*

## The problem

Sending the nearest ambulance sounds straightforward until every nearby vehicle
is busy. A vehicle finishing a job soon might reach a new call first. Moving an
idle ambulance can shorten the next response, but it can also leave another area
without cover.

Dispatch models these decisions on a city grid. Ambulances start at a hospital,
travel takes one minute per block, and calls become known only when they arrive.
The solver must work with the information available at that moment.

## How it works

Our solver combines assignment planning with adaptive positioning:

1. It tracks reported calls and when each ambulance will become available.
2. It plans waiting calls together. Small queues use exact dynamic programming.
   Larger queues use mixed-integer optimization through HiGHS, with a time limit.
3. It moves available ambulances to standby locations that improve response
   coverage as demand changes.

Once an ambulance accepts an emergency assignment, that commitment stays fixed.
The planner never reads future calls.

The visualizer replays the resulting schedules in top-down, 3D, and timeline
views. You can compare algorithms side by side, inspect individual calls, and
export a run as a GIF at the selected playback speed.

## Results

Across **30 bundled scenarios and 944 calls**, our adaptive solver achieved a mean
response time of **78.4 simulated minutes**. That is 66% lower than the closest-idle
baseline and 38% lower than greedy earliest arrival.

| Algorithm | Mean response, min | Scenarios won |
|---|---:|---:|
| **Adaptive dispatch, our submission** | **78.4** | **21** |
| Hybrid planner, vehicles wait at base | 79.3 | 7 |
| Adaptive posts | 81.0 | 8 |
| Nearest neighbour | 88.2 | 7 |
| Hungarian matching | 88.4 | 7 |
| Greedy earliest arrival | 127.3 | 3 |
| Dispatch greedy, vehicles wait at base | 133.6 | 3 |
| Closest idle, first come first served | 229.7 | 3 |

Response time measures the delay between a call arriving and an ambulance reaching
it. Means include all 944 calls. Tied algorithms each receive a scenario win.
These results describe the bundled grid simulations.

All 240 schedules in this comparison passed the independent rule checker. It
checks travel and service times, assignment commitments, and whether every call
receives service.

The [benchmark notes](docs/BENCHMARKS.md) contain further experiments, runtime
measurements, and limitations. The comparison above comes from the
[bundled replay traces](viz/public/traces/manifest.json).

## Try it locally

To explore the visualizer, install Node.js 24 or newer, then run:

```bash
git clone https://github.com/TalentedB/Dispatch.git
cd Dispatch/viz
npm ci
npm run dev
```

Open the local URL printed in the terminal, usually `http://localhost:5173`.
The repository includes replay data, so you can explore the scenarios without
running the Python solvers. Press `F` for the full-screen demo view.

### Run the solver

Use Python 3.10 or newer. From the repository root, create a virtual environment:

```bash
python -m venv .venv
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

Or in Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Then install the dependencies and run an example:

```bash
python -m pip install -r requirements-dev.txt
python -m dispatch inputs/brief_2_vehicles.txt
```

The solver prints each vehicle's schedule. Our submission appears in the
visualizer as `Submission: Adaptive + DP + MILP` and uses the internal ID `strategy4`.

### Compare and replay

Run the benchmark to check and score every configured solver against every input:

```bash
python bench.py
```

Generate a trace for a single run, then load the JSON file in the visualizer:

```bash
python -m dispatch inputs/brief_2_vehicles.txt --trace run.json
```

To regenerate the visualizer's traces for all solvers and scenarios:

```bash
python -m tools.export_viz
```

See the [visualizer guide](viz/README.md) for playback controls, GIF export,
trace generation, and the format for adding another algorithm.

## Project guide

| Location | Contents |
|---|---|
| [`dispatch/`](dispatch/) | Our dispatch planner, simulation, and adaptive coverage logic |
| [`solver/`](solver/) | Baseline dispatch algorithms |
| [`fleet/`](fleet/) | The adaptive-posts algorithm |
| [`viz/`](viz/) | The React visualizer and bundled replay data |
| [`tester/`](tester/) | Input parsing, schedule validation, and scoring |
| [`inputs/`](inputs/) | Example, edge-case, and generated scenarios |
| [`tools/`](tools/) | Trace export, input generation, and benchmark scripts |
| [`tests/`](tests/) | Python tests |

Read the [architecture and model](docs/ARCHITECTURE.md) for the simulation rules
and planning approach.

## Tests

From the repository root, with the Python environment active:

```bash
python -m pytest -q
```

From `viz/`:

```bash
npm test
npm run lint
npm run build
```

## Dependencies

The solver uses [HiGHS](https://highs.dev/) through `highspy` for mixed-integer
optimization and NumPy for numerical work. The visualizer uses React, TypeScript,
and Three.js. See the [visualizer dependency list](viz/README.md#third-party-code)
and [package manifest](viz/package.json) for its libraries.
