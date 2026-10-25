# Dispatch Visualizer

A React app that replays solver schedules on the city grid: scrub through the
day, play at any speed, switch algorithms, and run two side by side.

```bash
cd viz
# Node 24+ (also required by the native TypeScript playback tests).
npm ci
npm run traces     # runs every solver in ../solvers.txt on every input -> public/traces/
npm run dev        # http://localhost:5173
```

`npm run traces` is `python -m tools.export_viz` from the repo root. Use
`--only greedy,hungarian` or `--inputs "inputs/brief_*.txt"` to limit it.

The exporter also includes **Strategy 4: adaptive hybrid**. Install the root
`requirements-dev.txt` in your active Python environment first. It uses exact
small-queue dynamic programming and time-limited MILP for larger known queues,
with adaptive staging. Emergency commitments remain locked and future calls
are hidden from the online planner. `milp` is the same hybrid planner with base
deployment; `dispatch_greedy` is its event-driven greedy baseline. The original
four mainline algorithms are preserved.
Strategy 4 keeps free vehicles at coverage-selected resting sites after its
last known job. There is no end-of-file hospital return. A movement toward the
hospital can still be a legitimate coverage relocation, especially with one free
vehicle and a city centered on base. Base-deployment comparisons retain returns.

```bash
# From the repo root, using the active scheduler environment:
python -m tools.export_viz --only strategy4,milp,dispatch_greedy
python -m dispatch inputs/brief_small.txt --trace strategy4.json
# In viz/:
npm test
npm run build
npm run lint
```

Select Strategy 4 in either pane, or drop a standalone trace onto the app.
Native traces preserve call IDs and the actual x-then-y movement history,
including interrupted staging/return trips and zero-duration jobs. The existing
playback engine already renders `reposition` segments. Program runtime is measured
per process and shown separately from response delays. Optional `dispatch`
diagnostics retain per-replan proof statuses, gaps, fallback reasons and reported
map bounds; an optimal replan does not establish a globally optimal online day.

Exports are incremental: `--only` updates selected traces while retaining other
algorithms, scenarios and files. Failed runs return a nonzero exit status and are
removed from that scenario's manifest entries. The exporter runs each solver
once, requests `--trace` for `python -m dispatch` commands, and retains legacy
text replay for all other commands. The default process timeout is 20 seconds.
The app remains a playback frontend; Python/HiGHS run during trace generation.

Coverage is availability-aware. The 3D terrain and coverage heatmap use remaining
busy minutes plus Manhattan travel from where an ambulance becomes free. Native
readiness snapshots include currently reported queued work and are sampled only
at or before playback time. Legacy traces, without queue history, use the current
locked job's remaining travel/service. The terrain's free-only option includes
interruptible repositioning and return travel. Physical vehicle markers always
stay on their actual routes; projected readiness never teleports a vehicle.
The deployment planner refreshes these forecasts while jobs are in progress,
checks more closely near readiness, and moves only uncommitted, unqueued vehicles.

The city is centered on base and grows only when calls are reported. It starts
at `[-5,5]` on both axes (10 × 10 blocks) unless a native trace configures another
initial extent. A reported call at `(7,0)` changes it to `[-7,7]` on both axes
(14 × 14 blocks). Negative coordinates follow the same rule. Top-down, 3D and
heatmaps use the currently sampled map size, including when scrubbing backwards;
future calls and future route endpoints never determine the viewport. The map
size label counts blocks, while boundary intersections are included in coverage.
When bounds expand, the top-down and 3D cameras ease to the new fit over 420 ms.
The logical city size and report events update immediately; only the camera
interpolates. Repeated expansions retarget from the visible camera position.
Dragging, scrolling or orbiting cancels the automatic zoom. Reduced-motion
preferences use an immediate camera fit instead. Initial loading has no zoom-in
animation.

## What you can do

| Control | |
|---|---|
| Scenario picker | every input file, grouped (brief / custom / generated / uploaded) |
| Single / Side by side | one or two panes; both follow the same clock |
| Per pane | algorithm, view, view options, overlay layers |
| Transport | play/pause, ±1 min steps, jump to start/end, speed 1–120 sim-min/s; the scrubber shows each algorithm's busy-vehicle curve and red ticks where calls come in |
| Inspector | **Compare**: checker metrics for every algorithm on this scenario, best value in bold, `L`/`R` buttons load an algorithm into a pane. **Log**: the printed schedule, synced to the clock (click a line to jump to it). **Legend** |
| Keyboard | `Space` play/pause · `←/→` ±1 min (`⇧` ±10) · `[` `]` speed · `Home`/`End` |
| Demo mode | *Demo* button or `F`: full-screen map with floating controls; `Esc` leaves. Link straight in with `?demo&scenario=rush_hour_1` |
| Drag & drop | drop trace JSON files anywhere to add them |

### Views

| View | Shows |
|---|---|
| **Top-down** | The whole grid, north up. Base, emergencies (diamonds: red pulsing = waiting, amber = vehicle en route, rose = being attended, green dot = resolved) and vehicles. Scroll to zoom, drag to pan, double-click to reset. |
| **Isometric 3D** | The grid as terrain. Height and colour = estimated response minutes, including busy time and travel from projected readiness locations (option: free vehicles only, or flat). Each open emergency is a pillar showing its own wait/response. Drag to orbit. |
| **Timeline** | A Gantt chart: one lane per vehicle, coloured by state, with the waiting-calls count underneath. Click or drag to seek. |

### Overlays (toggle per pane under *Layers*)

| Overlay | Top-down | 3D | Timeline |
|---|---|---|---|
| Assignment state: halo and badge per vehicle (idle, en route, on scene, returning, repositioning) | ✓ | ✓ | call ids on jobs |
| Distance to assignment: remaining route and blocks to the assigned emergency | ✓ | ✓ | |
| Time to complete: ETA to the scene, minutes until the job is done, on-scene progress rings, wait times | ✓ | ✓ | wait and drive bars per call |
| Trails: the last 45 minutes of driving | ✓ | ✓ | |
| Coverage heatmap: response time including remaining busy work | ✓ | (it's the terrain) | |
| Upcoming calls: calls arriving in the next hour (the algorithms can't see these) | ✓ | ✓ | |

## Trace contract

Every pane renders a **trace**: one algorithm's run on one scenario. Types:
[`src/contract/trace.ts`](src/contract/trace.ts). Schema id `uvec.trace/v1`.

```jsonc
{
  "schema": "uvec.trace/v1",
  "algorithm": { "id": "greedy", "label": "optional", "description": "optional" },
  "scenario":  { "id": "brief_small", "label": "brief small", "group": "brief", "vehicles": 1 },
  "calls": [ { "id": 0, "time": 720, "x": 5, "y": 0, "duration": 2 } ],   // minutes since midnight, +x east, +y north
  "vehicles": [
    { "id": 0, "segments": [
      { "kind": "to_job",  "start": 720, "end": 725, "path": [[0,0],[5,0]], "callId": 0 },
      { "kind": "on_job",  "start": 725, "end": 727, "path": [[5,0]],       "callId": 0 },
      { "kind": "to_base", "start": 727, "end": 728, "path": [[5,0],[0,0]], "interrupted": true },
      { "kind": "to_job",  "start": 728, "end": 730, "path": [[4,0],[6,0]], "callId": 1 }
    ] }
  ],
  "span":    { "start": 715, "end": 744 },          // optional, computed if missing
  "check":   { "valid": true, "errors": [] },       // optional, from tester/checker.py
  "metrics": { "avg_response": 4.5 },               // optional, any numeric keys
  "log":     [ { "time": 720, "vehicle": 0, "text": "Vehicle 0: 12:00 Start route to job" } ] // optional
}
```

Rules:

- `kind` is one of `to_job`, `on_job`, `to_base`, `reposition`, `idle`.
- `path` lists grid corners in the order driven. Vehicles move 1 block/min along it, so
  a vehicle's position at time `t` is `t - start` blocks along the path.
- Segments are in time order and don't overlap. Between segments a vehicle is idle wherever the last one ended.
- `interrupted: true` marks a drive cut short at `end`, e.g. a return to base redirected to a new call.

### Connecting an algorithm

1. **Text route (no frontend code):** make the solver print the brief's output format, add it to
   `../solvers.txt` (the same file `bench.py` uses), then run `npm run traces`. The exporter replays
   the printed schedule into segments and attaches the checker's verdict and metrics.
2. **Native route (any language):** write `uvec.trace/v1` JSON yourself and drop the file on the app,
   or put it in `public/traces/` and list it in `manifest.json`. Use this for states the brief's text
   can't express, like `reposition` (moving to a standby point) or `idle` away from base.
3. *(Optional)* give it a name, description and colour in `src/algorithms/registry.ts`. Unknown ids
   work without an entry.

For the hybrid scheduler, use `dispatch/trace.py` and `--trace` rather than text
replay: legacy output cannot unambiguously identify duplicate calls and staging
movements. Native paths end at their actual traversed endpoint, so a redirected
vehicle does not jump to its former target. Default traces include the physical
initial staging at minute zero; use `--start-time` to configure a different start.

## Extending the frontend

```
src/
  contract/trace.ts        the trace types + validator
  engine/sample.ts         prepare(trace), sampleFrame(prepared, t): positions, states, ETAs, call states
  engine/status.ts         labels/colours for vehicle states and call states
  algorithms/registry.ts   optional per-algorithm display metadata
  views/                   view plugins (registry.ts lists them)
  overlays/                overlay plugins (registry.ts lists them)
  playback/clock.ts        the shared clock (time, speed, play state)
  data/traces.ts           manifest + trace loading, uploaded traces
  components/              Pane, Transport, Inspector (shadcn/ui based)
```

**New view:** create a `ViewPlugin` (`views/types.ts`) and add it to `VIEWS` in `views/registry.ts`.
It gets `{ prepared, frame, overlays, options }` and declares a `slot` (`map2d`, `map3d` or `gantt`), so
the pane knows which overlays it can host. It can also declare `options`, which the pane renders as selects.

**New overlay:** create an `OverlayPlugin` (`overlays/types.ts`) with a renderer for each slot it
supports, and add it to `OVERLAYS` in `overlays/registry.ts`. It appears in the Layers menu of every
view whose slot it implements. Renderers get the sampled `frame` plus slot helpers: `sy`/`px` for the 2D
map, `heightAt` for the 3D terrain, `tx`/`laneY` for the timeline.

**New vehicle state:** add the kind to `SegmentKind` and an entry in `VEHICLE_STATUS`.

## Third-party code

All open source: React (MIT), Vite (MIT), TypeScript (Apache-2.0), Tailwind CSS (MIT),
shadcn/ui components (MIT, copied into `src/components/ui/`), Base UI (MIT),
class-variance-authority (Apache-2.0), cn (MIT), tw-animate-css (MIT), three.js (MIT),
@react-three/fiber (MIT), @react-three/drei (MIT), lucide-react icons (ISC),
Geist font via @fontsource-variable/geist (OFL-1.1).

## UI design

The isolated redesign branch is `codex/ui-redesign`. The interface uses the
Hallmark Coral palette as a restrained light workbench, with the existing locally
bundled Geist font. `src/tokens.css` contains the shared surface, type, spacing,
semantic state and series colors. `src/lib/theme.ts` resolves those tokens for
canvas and WebGL, so 2D, terrain and chart paint share the same source.

The map, view controls and playback lead the screen. The inspector uses ruled
metric sections rather than nested cards. On narrow screens it opens over the
workspace and can be closed with the Inspector button; playback remains visible.
The simulation controls and the trace, view and overlay contracts remain in their
existing modules. A scalar scrubber now renders one thumb, and global playback
shortcuts yield to focused inputs, buttons and menus.

All statistics come from the checked traces. There are no invented metrics or
external photo assets. Data color identifies algorithms, vehicles and states;
interface color stays neutral. Decorative halos and pulses were removed, and
reduced-motion preferences disable UI animation.

For visual changes, run `npm run build` and `npm run lint`. The redesign was also
checked with browser interactions for uploads, algorithms, layers, playback,
top-down, 3D, Gantt, split panes, inspector tabs and widths from 320 to 1920px.
The existing solver, checker and trace-export tests remain unchanged.
