# UVec2026 — Emergency Vehicle Dispatcher

Requires Python 3.10+. The original `solver/` and tester use the standard library;
install `requirements-dev.txt` for the hybrid scheduler and tests.

## Solver

```bash
python3 -m solver inputs/brief_2_vehicles.txt                 # greedy (default)
python3 -m solver inputs/brief_2_vehicles.txt --mode hungarian
```

| Mode | Algorithm |
|---|---|
| `greedy` | Vehicle that can arrive soonest, including busy ones (chains the job) |
| `closest_idle` | Closest free vehicle (Manhattan); if none, calls wait and are served oldest-first |
| `nearest_neighbor` | Closest free vehicle; a vehicle that frees up takes the closest waiting call |
| `hungarian` | Free vehicles and waiting calls matched to minimise total distance (Kuhn-Munkres) |

Design, research and measured results: [docs/approaches.md](docs/approaches.md).
Compare modes on thousands of random scenarios: `python3 tools/stress.py`.

## Visualizer

```bash
python3 tools/export_viz.py        # run every solver in solvers.txt on every input -> viz/public/traces/
cd viz && npm ci && npm run dev
```

A React app (shadcn/ui, three.js) that replays the schedules. It has a timeline scrubber, play and
speed controls, any algorithm in any pane, and two algorithms side by side on a shared clock. Views:
top-down grid, isometric 3D terrain (height = drive time to the nearest vehicle), and a Gantt timeline.
Toggleable overlays show vehicle state, distance to the assigned emergency, time to complete,
trails, a coverage heatmap and upcoming calls. Algorithms plug in through a JSON trace contract.
Strategy 4 appears in the algorithm picker alongside the mainline algorithms.
It exports exact call IDs, staging paths, and service periods directly from the
simulation. To update just that algorithm without removing other comparisons:

```bash
python -m tools.export_viz --only strategy4
# Or export a standalone trace and drop it onto the frontend:
python -m dispatch inputs/brief_small.txt --trace strategy4.json
```

Trace generation requires the scheduler dependencies and uses the same Python
interpreter for subprocesses. Program runtime is shown separately from simulated
response time. This frontend replays completed runs; it does not run Python or
HiGHS in the browser. See [viz/README.md](viz/README.md).

## Hybrid scheduler and test bench

The original `solver/` algorithms and independent test bench remain available.
`dispatch/` adds the DP/MILP scheduler and adaptive coverage. Both feed the
existing visualizer through `uvec.trace/v1`; no separate frontend is required.

## Run the scheduler

Implementation proceeded after the requester confirmed authorization on
2026-10-25. The competition brief images remain unchanged in `prompt/`.

```bash
python -m venv .venv
# Windows PowerShell:
.venv/Scripts/Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m dispatch inputs/brief_small.txt
python -m dispatch inputs/brief_2_vehicles.txt --mode offline --report result.json
python -m dispatch inputs/brief_small.txt --scheduler greedy
python -m pytest -q
python bench.py --detail
```

Without activating the environment on Windows, replace `python` with
`.venv/Scripts/python.exe`. Generic `python`/`python3` entries in `solvers.txt`
use the benchmark's interpreter so dependencies remain in the same environment.

Online mode is the default: only reported calls may enter an optimization.
Strategy 4 is the application default for dispatch and deployment. Vehicles
originate at `(0,0)` at simulation minute zero, physically drive to coverage
positions, lock accepted jobs, chain queued work, and dynamically reposition
when resting. Use `--no-staging` for legacy base deployment and idle returns.
Strategy 4 also rebalances after the final known job and leaves vehicles at
coverage-selected resting locations. Ending the input does not send them home.
The hospital is a valid resting site when coverage selects it, especially for
one free vehicle covering the centered square.
Offline mode knows future calls,
but still waits until each report before departing toward that call; it may
wait at a previous incident instead of returning between future assigned jobs.

The default dispatch planner is a DP/MILP hybrid (`--scheduler milp` is retained
for compatibility). Queues of at most seven known calls use exact subset DP;
`--dp-limit 0` selects MILP only. Larger queues use actual HiGHS branch-and-cut.
Both use the same lexicographic objectives: total response,
worst response, travel, then vehicles deployed in the mutable plan. Defaults to
a 20-second whole-run budget, with a configurable 30-second per-replan
ceiling that is always limited by the remaining run allowance. Coverage uses deterministic grid calculations without a MILP deadline.
An incident solve can finish sooner when its optimum is proven. Runtime remains measured separately and is not added
to simulated emergency response. Diagnostics in
`--report` distinguish proven primary/lexicographic optima, feasible incumbents,
and validated retained/greedy fallback. Each plan reports its actual algorithm;
DP results are never labeled as MILP solves. A time/work-limited DP does not
claim optimality. Fallback reasons also go to stderr. Solver logs
never enter schedule stdout. Model construction counts against the budget but
can itself overrun a per-decision allowance; the benchmark enforces the external
20-second deadline. The application uses a shared budget with startup/output
reserves, queue-size DP allowances, and measured MILP construction costs. It
skips construction when that cost cannot fit. Unused coverage budget can be
spent on incident planning.

Unchanged queued routes are retimed and reused. New reported calls are inserted
into the previous feasible routes; that candidate is compared with fresh greedy
output. The better validated plan supplies the fallback and MILP starting
solution. HiGHS is seeded after objective setup so that setup cannot discard it.
Accepted incident travel/service remain outside these mutable routes.

## Strategy 4 coverage and redeployment

```bash
python -m dispatch inputs/brief_small.txt --staging --bounds -5 10 -5 10 --coverage-objective center --report staging.json
python -m dispatch inputs/brief_small.txt --staging --coverage-objective median --relocation-weight 0.2
python bench.py --solver "staged=python -m dispatch {input} --staging" --allow-reposition
python check.py inputs/brief_small.txt .bench_out/staged/brief_small.out --allow-reposition
python -m tools.benchmark_dispatch --output .bench_out/metrics.json
python -m tools.benchmark_dispatch --inputs "inputs/*.txt" "inputs/generated/*.txt" --variants greedy,milp,strategy4,greedy-staged --workers 4 --output .bench_out/strategy4-shipped.json
```

The map is a square centered on the hospital. Default bounds `(-5,5,-5,5)`
span 10 × 10 blocks (11 × 11 intersections, including both edges). Only reported
calls expand it. A call at `(7,0)` changes both axes to `[-7,7]`: 14 × 14 blocks.
The radius is the largest absolute known coordinate or configured initial extent,
and never shrinks during a run. Custom `--bounds` are enclosed in that centered
square. Future calls cannot resize the map, even in offline incident mode.
The frontend uses the bounds at the current playback time, so scrubbing backwards
restores the earlier map. Future route endpoints do not affect its camera or grid.
Emergency coordinates are never clamped.
Off-base staging is enabled for the requested Strategy 4. Select `--no-staging`
when base deployment is required. Vehicles physically drive to sites starting at
`--start-time` (default 0); calls can interrupt them en route.

The adaptive grid planner balances worst estimated response time (or mean
response with median coverage) against relocation travel and movement count.
All ambulances contribute: a busy vehicle contributes its remaining locked
travel/service and known queue time plus Manhattan travel from its eventual
ready location. Only free, unqueued vehicles receive relocation targets.
Coverage refreshes while work is in progress, with a default maximum interval
of 10 simulation minutes (`--coverage-availability-interval`), shortening the
interval near readiness. Relocation improvement thresholds still prevent churn.
Busy time is added in minutes; using a Euclidean Z-axis would undercount waiting
and grid travel. A long-busy vehicle can still make the hospital the best spare
location; a nearly available vehicle can shift the spare toward another area.
It uses exact enumeration for tiny grids and deterministic placement improvements
for larger ones, with cached distances and safe candidate pruning. The larger
search has no global optimality claim. `--relocation-weight`,
`--deployment-weight`, `--coverage-cooldown`, and `--min-coverage-improvement`
control the tradeoff. The legacy `--coverage-time-limit` option accepts positive
values for compatibility; zero disables coverage planning. All calls must occur
at or after `--start-time`. JSON records map expansion history, planner status,
predicted nearest-response area percentages (ties shared equally), and whether demand was
sampled on a large map. Percentages describe eventual targets, not current
coverage while ambulances are moving.
The dispatch coordinates `(X,Y,Z)` represent the location where a vehicle will
become free and its remaining busy time in minutes. A free vehicle has `Z=0`
at its actual position; a committed vehicle includes its remaining travel and
service. MILP minimizes response time directly, counting waiting and Manhattan
travel once. Z is not a Euclidean coordinate or a statistically normalized score.
Expected locked arrivals do not trigger incident solves. On expected completion,
the validated queued suffix is reused unless another free vehicle has moved.
Reports, changed free positions, and relevant future-dispatch wakeups can replan.
JSON metrics include incident solve and reused-plan counts.
Coverage adds explicit `Start route to staging` / `Arrive at staging` actions;
these require the checker/bench's opt-in flag. Ordinary output remains unchanged.
The bench and diagnostic wrapper enforce a 20-second timeout per complete
simulation by default. `--run-time-limit` controls the application budget and
`--timeout` controls the benchmark process deadline. Startup/output reserves and
shared incident/coverage allowances keep individual solves from consuming the
entire run. When budget is exhausted, coverage holds existing targets and
incident scheduling explicitly reports validated retained/greedy fallback. Diagnostic reports record
the selected limits, runtime, proof flags, gaps, and fallback use after every run.
The shipped-scenario correctness tests explicitly retain their original
0.25-second budget; the quality benchmarks use the shared application budget.
The diagnostic wrapper compares `greedy` and `milp` with base returns against
`greedy-staged` and `strategy4` with identical dynamic coverage. It uses the
application's default bounds unless explicitly overridden. `--workers` runs
independent benchmark subprocesses concurrently; its default is one. Runtime
remains diagnostic and never changes the response objective. `bench.py`'s
registered legacy comparisons explicitly use `--no-staging`.

See [the model and architecture](docs/ARCHITECTURE.md) for constraints,
movement rules, objective bounds, failure handling, and limitations, and
[measured benchmarks](docs/BENCHMARKS.md) for results and reproduction commands.

## Quick start

1. Write a solver in any language. It takes an input file path as an argument and
   prints the schedule to stdout in the brief's format.
2. Register it in `solvers.txt`:
   ```
   greedy = python3 solvers/greedy.py {input}
   ```
3. Run the bench:
   ```bash
   python3 bench.py                         # all solvers x all inputs
   python3 bench.py --detail                # plus one table per input
   python3 bench.py --only greedy --inputs "inputs/generated/rush*.txt"
   python3 bench.py --solver "test=python3 scratch.py {input}"   # one-off, no solvers.txt edit
   python3 bench.py --sort total_drive
   ```
4. Dig into a failure:
   ```bash
   python3 check.py inputs/brief_small.txt .bench_out/greedy/brief_small.out
   python3 solvers/greedy.py inputs/brief_small.txt | python3 check.py inputs/brief_small.txt -
   ```

## What gets checked

`tester/checker.py` replays the output line by line, tracking every vehicle, and flags:

- lines not in `Vehicle N: HH:MM <action>` format, unknown actions, vehicle ids outside the fleet
- lines out of chronological order (wrapping past midnight is fine)
- leaving for a call before the call comes in
- a `Drive` that doesn't lead to an open call, or a return drive that doesn't lead to base
- `Start job` not exactly when the drive ends, `Finish job` not exactly after the job's duration,
  `Arrive at base` not exactly when the return drive ends
- starting a new route while driving to or working another job (no switching)
- skipping `Arrive at base` when a vehicle would already be home
- calls never served and vehicles that never finish; legacy mode also requires a final return to base

It deliberately does **not** assume a strategy. Any valid choice passes, including
which axis a vehicle drives first: a vehicle redirected on its way home may be
anywhere on a shortest path back to base. A trip of zero distance (e.g. a job at
the base) may leave out its `Drive` line.

## Metrics

| Column | Meaning |
|---|---|
| `valid` | runs that passed every check |
| `expected` | runs whose output exactly matches `inputs/<name>.expected` (whitespace-insensitive) |
| `avg_resp` / `max_resp` | minutes from a call coming in to its job starting (weighted by call count) |
| `avg_delay` | response time minus the drive from base: time lost because vehicles were busy |
| `drive_min` | total minutes driven by the fleet, including returns (partial ones too) |
| `veh_used` | vehicles that served at least one call (summed over inputs) |
| `wins` | inputs where this solver had the best `avg_resp` |
| `secs` | total runtime |

Metrics only count valid runs, and solvers with any failed run are listed last.
Raw outputs are saved under `.bench_out/<solver>/<input>.out`.

## Test inputs

- `inputs/brief_*.txt` — the three examples from the brief, with `.expected` outputs.
  Two arithmetic slips in the brief's printed outputs are corrected; see `inputs/README.md`.
- `inputs/edge_cases.txt` — out-of-order lines, a job at the base, a 0-minute job,
  `7W` with no space, simultaneous duplicate calls, a job running past midnight.
- `inputs/generated/` — 24 random scenarios (light day, rush hour, overloaded, clustered,
  one street, single vehicle, big fleet, burst). Regenerate or make more with
  `python3 tools/generate_inputs.py --seeds 5`; the scenario settings are at the top of that file.

Add your own by dropping a `.txt` into `inputs/` (plus a `.expected` if you know the answer).

## Layout

| Path | What it does |
|---|---|
| `bench.py` | Runs solvers x inputs, prints comparison tables |
| `check.py` | Full error report + diff for a single output |
| `solvers.txt` | `name = command` list of solvers to benchmark |
| `tester/inputs.py` | Reads input files |
| `tester/checker.py` | Replays and validates an output, computes metrics |
| `tester/runner.py` | Runs solver commands (with timeout), compares to `.expected` |
| `tools/generate_inputs.py` | Deterministic random input generator |
| `tools/stress.py` | In-process comparison of solver modes on many random scenarios |
| `tools/export_viz.py` | Runs the solvers and writes JSON traces for the visualizer |
| `viz/` | The visualizer (React + Vite), see `viz/README.md` |
| `solver/` | The dispatcher: `engine.py` (rules + simulation), `algorithms/` (one file per algorithm), `render.py` |
| `docs/approaches.md` | The four algorithms, their sources, and results |
| `tests/` | Tests for the tester itself (`python3 -m pytest`) |
| `dispatch/` | Subset DP, retained-plan/MILP planner, adaptive coverage, simulation and validation |
| `tools/benchmark_dispatch.py` | Extended metrics through the existing benchmark runner |

## Third-party code

The original `solver/` algorithms and tester use the Python standard library.
The visualizer's npm dependencies and licenses are listed in
[viz/README.md](viz/README.md#third-party-code).

The hybrid scheduler uses
[HiGHS/highspy](https://highs.dev/) 1.15.1 (MIT) for MILP branch-and-cut,
with NumPy (BSD-3-Clause) as its array dependency. Tests use
[pytest](https://pytest.org) (MIT); `requirements-dev.txt` includes it.
HiGHS's binary distribution contains its own third-party notices; retain those
when distributing the solver. No proprietary optimizer or external service is
required. The formulation, simulator, and benchmark extensions are local code.
