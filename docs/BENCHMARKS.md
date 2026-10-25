# Validation and benchmark results

Measured locally on Windows, Python 3.12.6, highspy 1.15.1, NumPy 2.5.4,
pytest 9.1.1, on 2026-10-25. Single solver thread, fixed seed. Wall times
depend on host load and include subprocess startup; the tables are observations,
not performance guarantees. Raw snapshots are [shipped](benchmark-shipped.txt),
[focused](benchmark-focused.txt), and [per-solve JSON](benchmark-metrics.json).

## Current DP/MILP hybrid, retained plans, and cost-aware budgets

Final validation: **153 tests passed in 38.57 seconds**. This is the duration
of the complete test suite, not a single input run. Every original test and
fixture remains. New independent enumeration tests cover DP objectives,
release times, busy anchors, duplicates, alternative secondary priorities and
fixed worst-delay floors. Failure tests verify retained-plan fallback and a
valid MIP starting solution after objective setup.

```bash
python -m pytest -q
python -m tools.benchmark_dispatch --inputs "inputs/*.txt" "inputs/generated/*.txt" --variants greedy,milp,strategy4,greedy-staged --workers 2 --output .bench_out/hybrid-certified-shipped.json
python -m tools.benchmark_dispatch --variants greedy,milp,offline,strategy4 --bounds 0 10 0 0 --workers 2 --output .bench_out/hybrid-certified-focused.json
```

The final shipped comparison passed **112/112 runs**, all below the 20-second
external timeout. Maximum runtime across all variants was **16.53 seconds**;
Strategy 4's maximum was **16.45 seconds**, with a **1.08-second median**.
Two independent subprocesses ran concurrently. The compatible names `milp`
and `strategy4` now use exact DP for queues up to seven and HiGHS for larger
queues. `--dp-limit 0` disables DP for MILP-only experiments.

| Metric, 28 inputs / 741 calls per variant | Greedy/base | Hybrid/base | Greedy/adaptive | Hybrid/adaptive (Strategy 4) |
|---|---:|---:|---:|---:|
| Valid runs | 28/28 | 28/28 | 28/28 | 28/28 |
| Total response delay (minutes) | 83,749 | 56,917 | 81,353 | 54,281 |
| Average response delay | 113.02 | 76.81 | 109.79 | 73.25 |
| Worst individual response | 729 | 638 | 730 | 634 |
| Actual travel | 24,216 | 21,212 | 23,428 | 20,554 |
| Median complete runtime (seconds) | 0.43 | 0.47 | 0.49 | 1.08 |
| Maximum complete runtime (seconds) | 1.60 | 16.53 | 4.39 | 16.45 |
| Sum of individual runtimes (seconds) | 13.33 | 83.78 | 29.57 | 99.95 |

Strategy 4 reduced aggregate response delay by **29.34%** versus the previous
Strategy 4 snapshot (76,820 -> 54,281 minutes), **35.19%** versus greedy/base,
and **33.28%** versus greedy with adaptive coverage. Against greedy/base it
improved/tied/worsened 24/1/3 inputs; against hybrid/base, 18/1/9; against
greedy/adaptive, 23/4/1. These compare complete policies, not an isolated causal
measurement of DP alone. Different budgets/host load can change time-limited
online choices. No whole-day global optimality is claimed.

### Exact results and fallback accounting

Strategy 4 generated 747 incident plans:

- 611 DP_OPTIMAL: exact proofs for every requested objective of that known queue.
- 135 FEASIBLE MILP: validated incumbent, without an optimality claim.
- 1 FALLBACK: retained validated prior plan, **not a fresh greedy fallback**.
- 412 additional unchanged-queue decisions reused retimed plans without solving.

Fresh-greedy fallback fell from **145 decisions in the previous snapshot to
zero**. All fallback (including retained) fell from 145/731 (19.8%) to 1/747
(0.13%). Base hybrid had 665 exact DP plans and 134 feasible MILP plans, with
zero fallback. Reported MIP gaps are distinct from DP proofs; no unproven plan
is counted as optimal. Coverage skipped 130 Strategy 4 planning decisions once
its allowance was exhausted, retaining existing targets. Map histories verify
that only report events expand bounds. Accepted incident travel/service remain
locked in every solver and fallback path.

Retained queues, bounded new-call insertion and fresh greedy candidates are
compared using the same objective priorities. The better feasible plan tightens
the MILP cutoff and provides its starting solution. Diagnosis found that setting
a HiGHS objective invalidates a previously supplied start; seeding now occurs
**after** objective setup, and seeding time is deducted before starting search.
This changed large-queue timeouts from losing the start to returning a validated
feasible incumbent. Cold solver initialization counts against whole-run time,
but is excluded from model-assembly cost learning.

Budget allocation now uses a shared deadline instead of shrinking each decision
to one twentieth of a fixed incident pool. DP allowances scale with queue/fleet
work; MILP allowances use measured assembly cost and reserve search time.
Models are skipped when they cannot fit, retaining the validated incumbent.
The application reserves time for completion/output, while the benchmark still
rejects a subprocess that exceeds 20 seconds. This is not a hard realtime
promise for arbitrary input sizes or external host stalls.

An earlier four-worker attempt recorded three TIMEOUT results, including plain
greedy, and was not used for these aggregate results. Serial replays of those
same cases passed in 0.36, 0.39 and 0.73 seconds; the subsequent complete
two-worker run above passed all 112 cases. The failed partial snapshot remains
in `.bench_out/hybrid-final-shipped.json` rather than being counted as valid.

The final focused comparison passed 20/20 runs. Average response remained
28.00 greedy/base, 19.09 online hybrid/base, 18.00 offline hybrid/base, and
21.27 adaptive Strategy 4 on the explicitly configured line map. Coverage still
does not dominate every trace. Report files distinguish each actual algorithm,
incumbent source, allowance, assembly time, DP label count, status and gap.

Snapshots: [shipped summary](benchmark-hybrid.txt),
[focused summary](benchmark-hybrid-focused.txt), and
[per-case/per-plan diagnostics](benchmark-hybrid-metrics.json).
Full schedules, assignments and movements are generated under
`.bench_out/hybrid-certified-shipped-solver-reports/` by the command above.

## Previous adaptive coverage and 20-second whole-run snapshot

Reproduction with the workspace virtualenv:

```bash
python -m pytest -q
python -m tools.benchmark_dispatch --inputs "inputs/*.txt" "inputs/generated/*.txt" --variants greedy,milp,strategy4,greedy-staged --workers 4 --output .bench_out/fast-adaptive-shipped.json
python -m tools.benchmark_dispatch --variants greedy,milp,offline,strategy4 --bounds 0 10 0 0 --workers 2 --output .bench_out/fast-adaptive-focused.json
```

All 112 shipped-case runs passed the existing independent replay checker.
The maximum complete subprocess runtime was **12.38 seconds**; Strategy 4's
maximum was **12.11 seconds**. The application computation budget and external
benchmark timeout were both 20 seconds per input, not per replan. Four independent
subprocesses ran concurrently; runtime therefore includes contention and startup.
Elapsed wall time is diagnostic and does not advance the simulation clock.

| Metric, over 28 inputs / 741 calls each | Greedy/base | MILP/base | Greedy/adaptive | MILP/adaptive (Strategy 4) |
|---|---:|---:|---:|---:|
| Valid runs | 28/28 | 28/28 | 28/28 | 28/28 |
| Total response delay (minutes) | 83,749 | 79,843 | 81,694 | 76,820 |
| Average response delay | 113.02 | 107.75 | 110.25 | 103.67 |
| Worst individual response delay | 729 | 719 | 730 | 701 |
| Actual travel | 24,216 | 23,574 | 22,940 | 22,244 |
| Median complete runtime (seconds) | 0.84 | 2.23 | 0.95 | 2.67 |
| Maximum complete runtime (seconds) | 1.45 | 12.38 | 5.89 | 12.11 |
| Sum of individual runtimes (seconds) | 23.98 | 107.72 | 46.52 | 125.16 |

Strategy 4 reduced aggregate response delay by **8.27%** versus greedy/base,
**3.79%** versus MILP/base, and **5.97%** versus greedy using identical adaptive
coverage. It improved/tied/worsened 22/1/5 inputs versus greedy/base, 19/1/8
versus MILP/base, and 18/6/4 versus greedy/adaptive. These are observations,
not guarantees about future online calls or global full-day optima.

Initial bounds were (0,9,0,9) for every adaptive run. Only report events expanded
the map; the same rule applies to offline incident mode. Accepted incident trips
and service remained locked. Coverage holds targets after its shared budget is
spent: 146 coverage decisions were skipped in Strategy 4. Of its 731 incident
plans, 573 proved the primary optimum, 567 proved all requested objective stages,
and 145 used explicit validated fallback. The remaining 13 were feasible MILP
incumbents without primary proof. Base MILP had 641 primary proofs, 635 complete
lexicographic proofs, and 147 fallbacks among 800 plans. Fallback and gap details
are preserved rather than being counted as proven MILP results.

The focused 20-run comparison also passed every run. Weighted average delays:
greedy/base 28.00, online MILP/base 19.09, offline MILP/base 18.00, adaptive
Strategy 4 21.27. Thus adaptive coverage helped the full shipped aggregate but
hurt this small focused aggregate versus online MILP/base. No policy dominates
every trace. The focused coverage map starts as the explicitly configured line
(0,10,0,0) and subsequently expands from reported calls.

Performance diagnosis replayed a captured seven-free-vehicle coverage decision
on bounds (-40,40,-39,40). Caching per-point distance vectors and using safe
lower-bound candidate pruning reduced it from 1.63s to 0.23s with identical
targets. Eight further center/median replay cases also retained their targets.
A two-vehicle default-grid plan now takes milliseconds; larger cases remain
bounded heuristic searches. The incident MILP now shares job-to-job arcs:
for ten vehicles / ten jobs this reduces model columns from 1,131 to 231.

Current snapshots: [summary](benchmark-adaptive.txt),
[focused summary](benchmark-adaptive-focused.txt), and
[per-case metrics, map histories, proof counts, gaps and fallbacks](benchmark-adaptive-metrics.json).
Full per-solve and movement reports are generated under
`.bench_out/fast-adaptive-shipped-solver-reports/` by the reproduction command.
The earlier sections below preserve historical runs of previous policies and
budgets; they should not be interpreted as current defaults.

## Existing tests and extensions

Baseline command: `python -m pytest -q` (using the workspace virtualenv).
Initial result: 33 passed, 3 failed due to Windows runner paths. After the
runner portability fix, all original 36 passed. The extended suite has 153
passing tests, including all 28 supplied inputs, independent exhaustive
incident/coverage oracles, queue/service/commitment rules, redirection, solver
failure and timeout injection, and exact physical-history validation.

No original tests or fixtures were removed. A different valid optimized schedule
need not exactly match a sample: validity and response score determine correctness.
The original expected sample corrections remain in `inputs/README.md`.

## Original 0.25-second comparison: 28 shipped scenarios, 741 calls

Command with the virtualenv interpreter:

```bash
python bench.py --solver "milp=python -m dispatch {input} --time-limit 0.25 --no-staging" --timeout 60 --detail
```

Original online comparison, no staging, 0.25-second per-replan budget (the
application default has since increased to 30 seconds):

| Metric | Greedy | MILP |
|---|---:|---:|
| Valid inputs | 28/28 | 28/28 |
| Total response delay (minutes) | 83,749 | 79,894 |
| Average response delay (minutes/call) | 113.02 | 107.82 |
| Maximum individual delay (minutes) | 729 | 710 |
| Total actual travel (minutes) | 24,216 | 23,294 |
| Vehicle-use count summed over cases | 90 | 90 |
| Best average-response cases, ties included | 10 | 23 |
| Total subprocess wall time (seconds) | 8.57 | 198.78 |

MILP improved average response in 18 cases, tied in five, and worsened it in
five. Aggregate response decreased about 4.60%, and travel about 3.81%. The worst
individual delay decreased by 19 minutes in this run. This is not guaranteed:
minimizing total response is primary, and secondary worst-delay optimization
cannot sacrifice it.
Online local improvements need not improve future decisions with unseen calls.

The greedy baseline uses the same event engine, movement rules and independent
checker; it assigns released calls in release/file order to the vehicle with
earliest feasible arrival, including current service commitments and queues.
There is no claim that MILP dominates it under a finite solve-time budget.
The broad bench table does not collect primary gaps; use the diagnostic wrapper
below when those are needed. Runtime includes model construction and process
startup, not just branch-and-cut. The bench timeout is separate from each solve's
budget and was increased to 60 seconds for complete daily simulations.

## Focused comparison with solver diagnostics

```bash
python -m tools.benchmark_dispatch --time-limit 1 --coverage-time-limit 2 --output .bench_out/metrics.json
```

This reuses `bench.run_one`, the existing replay checker, and its summary table.
It runs the three brief examples plus two new fixtures with greedy, online MILP,
offline MILP and staged online MILP. Each MILP replan has a one-second budget;
staging uses inclusive bounds `(0,10,0,0)` and a two-second coverage budget.

All four variants were valid on all five inputs. Weighted average responses
were 28.00 minutes for greedy, 19.09 for online MILP, 18.00 for offline, and
18.55 for staging. These are different information/positioning policies, not
an assertion that coverage is always beneficial.

Per-solve JSON records assignment times in individual CLI reports and summarizes
status, objective, primary gap, execution time, proof flags and fallback reasons
in the benchmark report. In this snapshot, all 53 MILP replans proved their
primary optimum, each with primary gap zero; no fallback occurred. A previous
run exhausted a cold-start replan's budget during construction, illustrating
why fallback must remain explicit. Failure/timeout regressions test those paths
independently. Coverage has separate status,
gap, travel, objective metrics and timing.

The report also includes total/average/worst response, total travel, relocation
travel and fleet utilization. Utilization here is service minutes divided by
fleet size times elapsed simulation time, including time from the configured
start (midnight by default) to the actual final return. Stale canceled events
do not extend that denominator.

### Independently verifiable duration case

`tests/fixtures/duration_order.txt`: one vehicle at base; at 12:00 a job at
x=1 lasting 100 minutes and a job at x=2 lasting zero minutes are reported.

| Order | Response delays | Total |
|---|---|---:|
| Greedy long job first | 1, 102 | 103 |
| MILP short job first | 2, 3 | 5 |

Both routes travel four minutes including the final return. These are the only
two orders. The MILP establishes optimality; the duration reversal test changes
the optimal order. Separate pytest cases exhaustively enumerate four-job route
partitions over one, two and three ambulances, comparing all four objectives.

### Measurable coverage example

`tests/fixtures/coverage_line.txt`: one ambulance, line demand x=0..10,
call at x=10 at 00:20 with one-minute service.

| Configuration | Response delay | Pre-call relocation | Actual total travel |
|---|---:|---:|---:|
| Hospital-only | 10 | 0 | 20 |
| Staged at the line center | 5 | 5 | 20 |

The staged vehicle drives from base to x=5 before the call; it is not placed
there instantaneously. In the same focused run, staging worsened the duration
case from five to seven response minutes because its pre-call location differed.
Another test explicitly shows a call arriving during initial relocation and
checks dispatch from the intermediate position. Small p-center and p-median
instances are checked against all combinations of candidate sites. Dynamic
redeployment tests verify immediate replanning of remaining vehicles on dispatch
and replanning after release, without overriding commitments.

To collect extended metrics on the larger scenarios:

```bash
python -m tools.benchmark_dispatch --inputs "inputs/generated/*.txt" --variants greedy,milp --time-limit 0.25 --output .bench_out/generated-metrics.json
```

Use `--variants greedy,milp,offline,staged` to compare all policies and `--bounds`
to set the coverage experiment. Runtime and time-limited decisions can vary;
keep policy, seed, solver build, limits and inputs fixed for meaningful comparisons.

## Limitations of the evidence

Exhaustive small cases establish correctness for those instances, not for every
possible input. All supplied schedules pass independent replay, but daily online
outputs do not carry global optimality certificates. A proof flag applies only
to its exact mutable MILP subproblem. Static coverage and incident scheduling
remain separate models. Very large queues or grids need more solve/model-build
time; fallback remains explicit and valid. Traffic and uncertain future demand
are not modeled. See [architecture](ARCHITECTURE.md) for further tradeoffs.
