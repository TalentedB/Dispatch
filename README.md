# UVec2026 — Emergency Vehicle Dispatcher

Requires Python 3.10+, standard library only (`pytest` for tests).

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

---

# Solver Test Bench

A black-box tester for emergency-dispatch solvers. It runs any number of
solver programs on a set of inputs, checks every output against the rules in
the brief, scores it, and prints a comparison table. It shares no code with
`solver/`, so it acts as an independent judge.

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
- calls never served, vehicles that never finish or never return to base

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
| `solver/` | The dispatcher: `engine.py` (rules + simulation), `algorithms/` (one file per algorithm), `render.py` |
| `docs/approaches.md` | The four algorithms, their sources, and results |
| `tests/` | Tests for the tester itself (`python3 -m pytest`) |

## Third-party code

None at runtime. Tests use [pytest](https://pytest.org) (MIT license).
