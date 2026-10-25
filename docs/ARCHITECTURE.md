# Dispatch architecture and mathematical model

## Existing project and integration

The original inspection below describes the branch's starting point. The branch
has since been rebased onto mainline `99ac8cc`, retaining its four `solver/`
algorithms and React visualizer. `dispatch/trace.py` now adapts completed hybrid
simulations to the existing `uvec.trace/v1` contract. The native adapter carries
exact call IDs and traversed x-then-y paths, including interrupted repositioning.
`python -m dispatch ... --trace path.json` emits the trace while preserving text
stdout and the existing diagnostic report. The independent checker validates the
schedule before export. `tools/export_viz.py` requests this native file from
dispatch subprocesses and keeps text replay for mainline solver commands.

The visualizer's existing sampling engine, views, and overlays consume these
segments without a new simulation engine or backend service. Its algorithm
registry names the hybrid variants and its comparison panel tracks process
runtime separately. Trace regeneration is incremental and a failed run is not
advertised in the manifest. Optional native diagnostics retain the map history
and per-replan algorithm, status, proof flags, gap, fallback reason and runtime.

Verification at frontend integration commit `3ed8119`: 330 pytest tests and 88 Node
playback tests passed. The exporter produced 87 valid native traces across all
29 mainline scenarios (three dispatch variants); the existing 116 mainline
traces were retained. Maximum measured process runtime was 16.18 seconds, with
zero fallback plans. These runs include mainline's new `input_abdullah` scenario,
so their aggregate scores are not directly comparable to the historical
28-scenario benchmark snapshots. The frontend production build passes; lint
continues to report warnings in unchanged mainline components. Browser checks
covered Strategy 4 selection, initial staging, metrics, timeline completion and
the 3D view. Playback tests use Node's built-in test runner, without an additional
test framework dependency.

Inspection found a Python 3.10+ test bench, not an existing dispatch algorithm.
There was no AGENTS.md, solver, build process, or runtime dependency manifest.
`pyproject.toml` configures pytest. `tester/inputs.py` parses competition input
into immutable Call/Point objects and already implements Manhattan geometry.
`tester/checker.py` independently replays text output; `tester/runner.py` runs
arbitrary subprocess solvers; `bench.py` scores 28 supplied scenarios, and
`check.py` diagnoses individual schedules. All fixtures and original tests remain.
The six competition brief photographs were reviewed, including their sample
arithmetic inconsistencies already documented in `inputs/README.md`.

The first baseline run on Python 3.12.6 / Windows yielded 33 passing and three
failing tests. Failures were Windows backslash parsing and path-separator
assumptions in the runner. The runner now preserves native backslashes, passes
input paths with forward slashes, and resolves generic Python commands through
the bench interpreter. All original 36 tests then passed without fixture changes.

Components and dependency direction:

| Component | Responsibility |
|---|---|
| `tester/inputs.py` | Existing parser, Point, Call, BASE and Manhattan distance |
| `dispatch/model.py` | Ambulance/Emergency state, immutable routes and movement segments |
| `dispatch/optimizer.py` | MILP construction, HiGHS execution/extraction and greedy baseline |
| `dispatch/dynamic.py` | Exact small-queue subset DP with Pareto time/cost labels |
| `dispatch/planning.py` | Retain/extend queues, choose validated incumbent, dispatch to DP or MILP |
| `dispatch/coverage.py` | Adaptive bounds, deterministic coverage search and vehicle matching |
| `dispatch/simulation.py` | Event heap, commitments, replanning, actual movement and output records |
| `dispatch/validation.py` | Independent plan and physical-history checks, active under python -O |
| `dispatch/__main__.py` | Existing input interface, CLI options, text output and optional JSON |
| `dispatch/trace.py` | Exact simulation history adapted to the mainline frontend trace contract |
| `tester/checker.py` | Existing external replay, extended for opt-in staging and duplicate durations |
| `tools/benchmark_dispatch.py` | Diagnostic collection using existing bench.run_one and summarize |

Models/validators do not import simulation or formatting. The simulation calls
the optimizers, and the CLI validates text output again with the existing
checker before printing it. No service, language migration, or new test framework
is introduced. The runner still accepts other languages and explicit interpreters.

## Reading and maintaining the algorithms

Public function names, domain fields, command-line options and report keys remain
compatible. Private implementation names describe the scheduling concept rather
than a tuple index or one-letter mathematical variable. Functions and variables
use snake_case; classes use PascalCase; policy constants use UPPER_SNAKE_CASE.
Black formats dispatch/ to 100 columns for Python 3.10; settings are in
pyproject.toml. Black is optional development tooling, not a runtime dependency.

Start at simulate(), which delegates to the private _Simulation.run() event loop.
Named _SimulationEvent and _DispatchDecision records make ordering and replan
triggers explicit. Separate methods handle reports, locked dispatch, arrival,
service completion, coverage and legacy base returns. _ComputationBudget owns runtime
accounting and names the existing policy constants; no scheduling policy changed.

planning.optimize() chooses the validated starting plan and DP/MILP strategy.
_insert_reported_call() handles bounded insertion independently of that choice.
The DP uses _RoutePrefix, _VehicleRoute and _FleetAssignment named records;
completion time, response delay, travel and job order are accessed by name.
_build_vehicle_routes() and _assign_next_vehicle() separate route optimization
from fleet allocation. _RoutingModel groups MILP variables and separates route
constraints, timing constraints, starting solutions and result extraction.

Coverage uses a named _CoverageScore and a private _CoverageSearch. Sampling,
minimum-cost vehicle matching, coverage scoring, starting placements, candidate
pruning and local improvement have separate descriptive functions or methods.
Comments explain mathematical invariants and solver behavior rather than narrate
assignments. Vectorized distance calculations and the existing search limits
remain intact.

The readability refactor passed all 153 tests and 80 deterministic comparisons
against archived pre-refactor sources: eight coverage, twelve DP, twelve MILP,
and 48 complete simulation cases. Those comparisons matched coverage targets,
objective values, schedules, physical movement and reported-map histories.
The full benchmark passed 112/112 runs, with a maximum runtime of 14.85 seconds.
See benchmark-readability.txt and benchmark-readability-metrics.json. Time-limited
search trajectories can vary with execution timing even when policies are the same.

## Hybrid planning and retained schedules

The compatible scheduler name `milp` now selects DP for at most seven pending
calls (`--dp-limit`, zero disables DP), and MILP for larger known queues.
Algorithm/status diagnostics distinguish them. Both share the same priorities,
release rules, availability anchors, independent validation, and 20-second
whole-run budget. Neither sees unreported calls in online mode.

When a report changes mutable work, filter previous vehicle queues to still
pending jobs, preserve their relative order, and insert new reported calls at
candidate positions. Insertion work is bounded; append candidates always ensure
completion. Retiming enforces current anchors, service times and call releases.
Compare against a fresh validated greedy plan using the configured objective
order and fixed worst-delay floor. Retain the better candidate. It supplies both
fallback and the complete MILP start/cutoff. Thus solver failure does not discard
a better previous schedule. Unchanged problems continue to reuse route suffixes
without optimization. Locked emergencies never appear in mutable queues.

### Exact subset DP

For each vehicle v, cache nondominated labels for `(served subset S, last job j)`:
`(completion T, accumulated response R, worst delay W, travel D, route)`.
A transition to unserved k is:

```
start = max(T, r_k) + Manhattan(j,k)
T_new = start + p_k
R_new = R + start - r_k
W_new = max(W, start - r_k)
D_new = D + Manhattan(j,k)
```

Initial labels use `max(now,a_v,r_j)+distance(source_v,j)` as service start.
At the same `(S,j)`, discard a label only when another is no worse in all four
numeric components. Keeping just earliest completion or least response would
be incorrect: these can trade off. Return-to-base travel is added at terminal
labels, including for unused vehicles. For each terminal subset, retain minimum
response and nondominated worst-delay/travel alternatives.

A second subset DP allocates disjoint job subsets across vehicles. Combine
response/travel/deployment counts by addition and worst delay by maximum,
including the fixed worst-delay floor. For identical allocated subsets and
processed vehicles, discard larger primary cost and then componentwise dominated
secondary costs. Final selection follows configured lexicographic priorities.
This preserves worst/travel tradeoffs even when another vehicle sets the global
worst response. Routes are independently validated after extraction.

The DP is exponential (vehicle subset partitioning alone has O(V*3^J) transitions,
before accounting for Pareto labels), so it has a small queue cutoff, deadline,
and 100,000-label work cap. `DP_OPTIMAL` means the complete search proved every
requested objective; `DP_FEASIBLE` retains a generated complete plan after a
limit. If no better complete DP plan is available, `FALLBACK` retains the validated
incumbent with an explicit source (`retained` or `greedy`). DP results have no
MILP optimality gap. Diagnostics include generated-label count and allowance.

## Incident MILP

At replanning time t, let J contain known uncommitted calls. For each vehicle v,
its virtual source has position q_v and availability a_v. An idle, returning or
repositioning vehicle is anchored at its actual position at t. A vehicle locked
to an incident is anchored at that incident's location and fixed completion
time. Its current incident is excluded from mutable work. Completed work is
also excluded. All these contributions to total response are constants.
This is Strategy 4's `(X,Y,Z)` readiness representation: `Z=max(0,a_v-t)`
minutes, with `(X,Y)=q_v`. Physical position remains separate. Unit travel time
already puts space and waiting in minutes; no statistical normalization or
three-dimensional Euclidean path length is used. Waiting is counted once in
`s_j-r_j`, including time a queued call has already spent waiting.

Call j has release r_j, location q_j and service duration p_j. Travel d_ij is
Manhattan distance, with signed coordinates and one minute per intersection.
The hospital is (0,0). No Euclidean approximation or city-bound clamping is used.

Variables:

- Binary b_vj selects vehicle v's first mutable job j; e_v means unused.
- Binary x_ij selects a shared job-to-job arc, and f_i ends a route after job i.
- Integer s_j is service start. Completion c_j = s_j + p_j is derived.
- Continuous ranks u_j in [1, |J|] eliminate subtours.
- W bounds every variable and already fixed individual response delay.

For each vehicle, sum_j b_vj+e_v=1. Each job has exactly one predecessor
(sum_v b_vj+sum_i x_ij=1) and one successor (sum_k x_jk+f_j=1).
Ranks prohibit disconnected cycles, so each job belongs to exactly one path
rooted at a vehicle's source. Following that path determines its ambulance.
There is no merging or branching and no possibility of switching vehicles.
Locked work remains outside the mutable routes and fixes each source anchor.

Job-to-job arcs are shared because their distance and timing do not depend on
vehicle identity. The previous model duplicated them for every vehicle. The
new model has O(J^2+V*J) variables/constraints rather than O(V*J^2).
For ten vehicles and ten pending jobs, model variables decrease from 1,131
to 231. This changes the formulation, not its feasible schedules or priorities.

For every job arc i -> j :

```
s_j >= s_i + p_i + d_ij - M_ij (1 - x_ij)
s_j >= r_j + d_ij - M_release_ij (1 - x_ij)
u_j >= u_i + 1 - |J| (1 - x_ij)
```

For a source -> j arc:

```
s_j >= max(t, a_v, r_j) + d_vj - M_source_vj (1 - b_vj)
```

Also s_j >= max(t, r_j), W >= s_j - r_j, and W is at least the
largest fixed response delay. The second arc constraint is essential: merely
requiring service after release permits advance travel. Here the vehicle must
wait at its predecessor until the call is reported. Departure is reconstructed
as max(predecessor completion, report time, current time), so every accepted route
is physically executable without advance emergency dispatch. Rank constraints
rule out cycles even when all relevant distances and durations are zero.

### Finite bounds and Big-M

First generate and independently validate a deterministic feasible greedy plan.
Let F be its total response delay over mutable calls. Add sum(s_j-r_j) <= F.
All delays are nonnegative, so a primary optimum has s_j <= U_j = r_j+F.
Let L_j = max(t,r_j). The bounds preserve at least the feasible baseline and
every potentially better primary schedule. Then use:

```
M_ij         = max(0, U_i + p_i + d_ij - L_j)
M_release_ij = max(0, r_j + d_ij - L_j)
M_source_vj  = max(0, max(t,a_v,r_j) + d_vj - L_j)
```

These are constraint-specific bounds, not arbitrary large constants. W has
upper bound max(F, fixed worst delay). The validated baseline is supplied as a
complete MIP start, including routes, starts, ranks and W. The better retained
incumbent replaces greedy when available. Supply the start after setting the
objective: HiGHS invalidates an earlier user solution on objective changes. A
regression checks that a valid starting solution reaches every solve stage.

### Objectives and solver outcomes

Sequential minimization, default order:

1. Sum_j(s_j-r_j).
2. W, including already fixed delays as a floor.
3. Selected arc travel, including each vehicle's final trip to base, even when
   its route contains no mutable jobs.
4. Number of vehicles used in this mutable plan.

`--priorities` may omit/reorder secondary objectives, but response must remain
first and priorities must be unique. No weighted sum can trade response away.
After a stage is proven optimal, its integer objective is fixed before the
next stage. If a stage times out, lower priorities are not attempted. The
default total per-replan budget is 30 seconds, measured from entry including
model construction. Construction is synchronous and can itself overrun the
budget; HiGHS receives only remaining time. This is not a hard process deadline.

HiGHS 1.15.1/highspy is an open-source MILP branch-and-cut solver under MIT,
chosen for native Python integration and Windows wheels. No CP-SAT substitution
is used. The gap targets are zero; threads=1 and a fixed seed provide repeatable
search on the same build. Time-limited searches may differ near a deadline on
different machines or under load. After adding an objective equality, solve
state is cleared and the validated incumbent is reseeded before the next stage;
this avoids stale incremental MIP presolve state observed in an enumeration case.

Each result reports routes, departure/start/completion times, total/max delay,
planned travel, objective, primary gap when available, elapsed time, and stage
statuses. OPTIMAL means every requested lexicographic stage was proven optimal;
primary_optimal separately records proof for response alone. FEASIBLE means a
validated incumbent exists but some requested stage lacks proof. EMPTY has no
mutable jobs. FALLBACK identifies independently validated retained/greedy output and its
reason/source; GREEDY explicitly selects the comparison algorithm. DP statuses
are described above and never imply an MILP solve.

Error/infeasible/no-incumbent statuses are never accepted as MILP solutions.
Invalid extracted routes are rejected. Selected routes are retimed to earliest
feasible integer execution and independently checked. A claimed primary optimum
must agree with this replayed objective. If a later stage fails, a previously
validated incumbent is retained. The gap in JSON is HiGHS's primary-stage gap,
not proof about an online day or a later coverage solve.

## Event simulation and physical commitments

The heap orders events by absolute integer minute and insertion sequence.
Reports, service completions, return/staging arrivals and scheduled wakeups
trigger dispatch decisions. Arrival at a locked emergency only changes its
execution status; its future completion anchor remains unchanged, so it does
not trigger an incident MILP. All existing events at a timestamp are applied
before replanning; zero-time consequences are then processed at that same time.
There is no per-minute simulation loop. Output records retain causal insertion
order among equal timestamps and are globally chronological.

Each ambulance distinguishes current physical position, destination, active
Movement, availability, committed assignment and mutable future queue. Movement
uses x first, then y, and is evaluated at the actual event time. Accepted
emergency travel and service are locked. Queued future work can change. Return
and staging travel are interruptible; truncating one records only its actual
distance and invalidates its old arrival event using a generation counter.
Each incident movement carries its call ID for independent exactly-once replay.

An expected completion reuses the existing queued route suffix, retimed and
independently validated against current anchors. It does not rebuild the MILP
unless another free vehicle has moved. New online calls, changed free positions,
or relevant future departure wakeups invalidate reuse. Missing/duplicate queued
jobs force a fresh solve. Reused routes do not receive new optimality claims or
inflate solve counts. Simultaneous reports are batched. Coverage cooldown wakeups
are coalesced and an empty resting fleet needs no coverage solve.

After completing a job, the vehicle can immediately chain another. If no work
is assigned, Strategy 4 makes it available for dynamic coverage. `--no-staging`
returns it to base instead. Strategy 4 keeps resting vehicles at coverage-selected
locations after the final known job; it has no mandatory end-of-input return.
The hospital may still be selected as a coverage location, especially when a
single free vehicle covers a square centered on the origin.
Output uses the existing combined
one/two-axis Drive syntax, including zero-distance routes without a Drive line.
The brief_small output is reproduced exactly with `--no-staging`. Duplicate same-place calls with
different durations are disambiguated by observed service duration in the
external checker; the text format itself has no call IDs.

Online mode supplies only reported pending calls to MILP. Event payloads contain
future reports but are not exposed to decision functions. There is no end-of-input
notification to the dispatcher: the finite test run ends when its pending events
have settled. Resting behavior before an unseen report is identical for a full
input and the same known prefix. Offline mode exposes all calls at the start
and during replans. It still forbids incident-directed departure before report;
it can wait at the previous job for a future assigned call. Returning to base
between such jobs is not mandatory. Both modes start at the hospital; base-return
deployment also finishes there. With `allow_reposition=True`, the checker accepts
completed jobs and settled staging off base, but still rejects unfinished travel
or service. The physical validator retains strict terminal-base checks for
base-return deployment. JSON records absolute times; text retains HH:MM rollover.

The incident planner's secondary travel estimate still includes a terminal
base-distance proxy when comparing mutable routes; it does not issue a movement.
Execution metrics report actual travel, including coverage relocation. Coverage
and incident routes remain separately optimized, without a full-day optimality claim.

The removal of forced terminal returns passed 336 Python tests and 94 frontend
tests. All 29 refreshed Strategy 4 traces are valid and contain zero `to_base`
segments. Maximum observed process runtime was 17.02 seconds. Four budget-limited
decisions reused validated retained plans (three run-budget limits and one DP
allowance limit); none used a greedy fallback. The frontend now initially selects
Strategy 4 when present, with base-return algorithms available for comparison.

## Adaptive coverage grid planner

Coverage no longer invokes HiGHS. The city is a square centered on `(0,0)` with
radius `R = max(initial radius, abs(x), abs(y))` over reported calls only. Its
bounds are `(-R,R,-R,R)` and its side length is `2R` blocks. The default radius
is 5: 10 × 10 blocks, with 121 grid intersections including the boundary. Custom
initial bounds are enclosed in a centered square before simulation begins.
A report at `(7,0)` expands a default city to 14 × 14 blocks. The map never
contracts during forward execution. Even offline
incident scheduling cannot expose future locations to coverage. The report's
map_history records every expansion time and bounds. Coverage records its own
time, bounds, area shares, runtime, and search status.

The frontend previously fitted its camera and grid to every call and movement
endpoint in a completed trace. Playback now builds a time-indexed history from
reported call times, seeded only by the native trace's configured initial extent
(or radius 5 for legacy traces). `sampleFrame` selects the extent at the sampled
time. Top-down, 3D terrain/camera, and the heatmap all use `frame.bounds`.
Scrubbing backwards restores an earlier square; future calls and future travel
endpoints cannot enlarge it. The top-down city is clipped to that square and the
map shows its current side length in blocks. This changes coverage/deployment
results, so earlier benchmark snapshots describe the prior rectangle policy.

The centered-square correction passed 333 Python tests and 90 playback tests,
including `(7,0)` producing a 14 × 14 city only at its report time, negative
coordinates, simultaneous reports, configured initial extents, native map-history
agreement and rewind behavior. All 87 native traces were regenerated and valid;
the maximum observed process runtime was 16.09 seconds with no fallback plans.
Browser playback confirmed the first report expands the grid and camera, and
rewinding restores the initial extent. Build passes; the existing frontend lint
warnings remain.

Only vehicles without locked work or queued incidents are movable coverage
decisions. Other vehicles remain fixed readiness anchors. For an intersection
q and time t, estimated response is the minimum of `Manhattan(target[v],q)` for
movable vehicles and `max(0,available[v]-t)+Manhattan(ready_location[v],q)` for busy
anchors. Ready locations/times include the current locked job and currently
reported queued jobs; unreported queue locations are excluded, even offline.
This is additive Manhattan distance in `(X,Y,Z)` where Z is busy minutes, not
Euclidean geometry. Minimize worst estimated response (center), or mean response
(median), plus relocation_weight times
actual remaining relocation travel and deployment_weight times vehicles moved.
Compare with continuing existing targets; move only when the score improvement
exceeds min_improvement. Cooldown coalesces rapid fleet/map changes. Timed checks
refresh availability at most every `availability_interval` simulation minutes
(default 10), halving the remaining gap down to one minute near the next readiness
time. Those planned availability checks can bypass the membership cooldown, but
still require the configured objective improvement to move. Obsolete wakeups are
ignored; no refresh loop remains once all vehicles are free. Coverage retains
its shared computation allowance and holds targets when that allowance is exhausted.
Actual physical
positions are evaluated at the decision time. Repositioning remains interruptible;
accepted emergency travel and service remain locked. All vehicles start at base
and physically drive to their targets. They continue resting at coverage targets
after the last known job; ending a test file does not trigger a return to base.

Area share means the percentage of demand intersections for which each vehicle
has the best predicted response, including busy-time penalties. Busy anchors
and free targets both have shares. Equal-response ties split equally, so shares
sum to 100 percent.
It is a distribution diagnostic, not the fraction reachable within a response
threshold, and equal shares alone are not the optimization objective. These
metrics describe eventual targets, not coverage during relocation.

The native trace records readiness snapshots when assignments/known queues change.
The playback sampler uses only snapshots at or before the selected time, subtracts
elapsed time from availability, and preserves current-job ETAs separately. The 3D
terrain and heatmap use the same additive response metric, including known queues
when native snapshots exist. Legacy imported traces fall back to the current
locked job's completion time because they contain no queue-plan history. Busy
vehicles remain physically locked; rendering readiness never changes their route.

For very small problems, enumerate candidate-site multisets and match vehicles
using the Hungarian algorithm (O(fleet^3)) to minimize weighted relocation cost.
If both relocation weights are zero, matching minimizes distance. Enumeration
on the complete grid is labeled OPTIMAL_ENUMERATION. Otherwise use bounded
coordinate descent from three deterministic starts: current destinations, a
farthest-point dispersed configuration, and balanced rectangular partitions. Each step evaluates all candidate sites;
matching then improves the vehicle-to-target assignment. This is HEURISTIC,
with no global optimality claim and no MILP gap. EXACT_CANDIDATES means exhaustive
search over a reduced candidate grid, not a full-map optimum.

Defaults use at most 225 regular candidate sites (plus current clipped targets
and a central intersection), four improvement passes per start, and enumeration
only up to 2,000 combinations. Demand uses every intersection up to 10,000 points.
Larger maps use at most 10,000 weighted rectangular-block representative points;
reported metrics are then approximate and sampled=true. Candidate coarsening
also makes large-map placement approximate, even with exact demand metrics.
Distance vectors are cached within each plan. For center coverage, distances
on a subset of hard demand points give lower bounds that safely reject losing
candidates before full-grid scoring. The cache/pruning differential check kept
the same targets in nine captured center/median cases. These work limits replace
coverage solver deadlines and are also subordinate to the whole-run budget. The old
--coverage-time-limit option is retained: zero disables planning; positive values
are accepted for compatibility but do not bound grid calculations.

## Validation, tests, and practical limits

The existing checker remains the machine-output oracle. New pytest cases reuse
it and independently enumerate small assignments, permutations and route cuts
to verify all lexicographic objectives. Small coverage grids enumerate all site
combinations. Failure tests inject solver errors, infeasible statuses, timeouts
with and without incumbents, and corrupt physical histories. All 28 supplied
scenarios are replayed. No original fixture or expected output was deleted.

The incident formulation has O(pending_calls^2 + vehicles*pending_calls) binary arcs; coverage
uses bounded candidate and demand grids. Large incident queues can
exhaust budgets or memory. Increasing time limits improves opportunities for
proof but does not guarantee better online outcomes. The per-replan incident ceiling
is 30 seconds, subordinate to the whole-run budget;
fallback remains a supported, visible outcome. Computation time is tracked but
does not advance the simulated emergency clock. The whole-run application budget and external benchmark
timeout default to 20 seconds. The CLI deducts startup time and reserves one
second for output; simulation stops admitting optimization work by 90 percent
of its remaining budget. Coverage has a 20-percent cap; incident planning can
use unused coverage time. DP allowance scales with V*3^J, capped at one second.
MILP allowance scales with an exponentially smoothed measured model-construction
cost (excluding one-off solver import/setup), with a 0.4-second floor and
two-second ceiling. Each decision can use at most 40 percent of remaining time.
If model construction plus a search margin cannot fit, skip it and retain a
validated feasible candidate. All import/setup/seed work still counts against
elapsed whole-run time; the search receives only time left after MIP seeding. Coverage checks its allowance between work units. Exhausted coverage holds
existing targets; exhausted incident planning uses explicitly labeled validated
retained/greedy output. Accepted trips remain locked in either case. The application
budget is cooperative, not an OS hard realtime guarantee; the benchmark timeout
enforces the external deadline and reports TIMEOUT if exceeded. Correctness
regressions on the shipped scenarios explicitly retain a short 0.25-second
budget; quality benchmarks exercise the application defaults.

Independent coverage and incident scheduling do not prove a globally optimal
full-day solution. An optimal MILP result proves the specified current subproblem.
Online decisions cannot predict future calls; a primary improvement can worsen
the worst individual delay. Coverage optimizes eventual static sites, not the
transient coverage along every relocation path, and may hurt response on a
particular future call. The threshold/cooldown mitigate oscillation, not all
coverage losses. Offline replanning under finite budgets is also not a whole-day
optimality certificate. Travel is unobstructed, unit-speed, deterministic Manhattan;
there are no traffic, hospital capacity, clinical urgency or stochastic service
models. Initial origins are currently fixed to base; staging controls where
vehicles subsequently drive. The original HH:MM checker infers midnight by clock
rollover, so exceptionally long unobserved gaps of a full day or more are
ambiguous in text; absolute JSON times avoid that limitation.

Future improvements: cache DP route tables across compatible decisions, tighten
arc sets, cache model/distance structures, support custom initial origins and
weighted demand, introduce explicit day annotations if the competition output
contract permits them, and evaluate coverage policies on held-out demand traces.
