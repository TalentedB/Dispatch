# Dispatch Visualizer

A React app that replays solver schedules on the city grid: scrub through the
day, play at any speed, switch algorithms, and run two side by side.

```bash
cd viz
npm install
npm run traces     # runs every solver in ../solvers.txt on every input -> public/traces/
npm run dev        # http://localhost:5173
```

`npm run traces` is `python3 tools/export_viz.py` from the repo root. Use
`--only greedy,hungarian` or `--inputs "inputs/brief_*.txt"` to limit it.

## What you can do

| Control | |
|---|---|
| Scenario picker | every input file, grouped (brief / custom / generated / uploaded) |
| Single / Side by side | one or two panes; both follow the same clock |
| Per pane | algorithm, view, view options, overlay layers |
| Transport | play/pause, ±1 min steps, jump to start/end, speed 1–120 sim-min/s; the scrubber shows each algorithm's busy-vehicle curve and red ticks where calls come in |
| Inspector | **Compare**: checker metrics for every algorithm on this scenario, best value in bold, `L`/`R` buttons load an algorithm into a pane. **Log**: the printed schedule, synced to the clock (click a line to jump to it). **Legend** |
| Keyboard | `Space` play/pause · `←/→` ±1 min (`⇧` ±10) · `[` `]` speed · `Home`/`End` |
| Drag & drop | drop trace JSON files anywhere to add them |

### Views

| View | Shows |
|---|---|
| **Top-down** | The whole grid, north up. Base, emergencies (diamonds: red pulsing = waiting, amber = vehicle en route, rose = being attended, green dot = resolved) and vehicles. Scroll to zoom, drag to pan, double-click to reset. |
| **Isometric 3D** | The grid as terrain. Height and colour = drive time from each intersection to the nearest vehicle (option: nearest *free* vehicle, or flat), so vehicles sit in valleys and badly covered areas are peaks. Each open emergency is a pillar whose height is the distance from its responding vehicle (or from the nearest vehicle while it waits). Drag to orbit. |
| **Timeline** | A Gantt chart: one lane per vehicle, coloured by state, with the waiting-calls count underneath. Click or drag to seek. |

### Overlays (toggle per pane under *Layers*)

| Overlay | Top-down | 3D | Timeline |
|---|---|---|---|
| Assignment state: halo and badge per vehicle (idle, en route, on scene, returning, repositioning) | ✓ | ✓ | call ids on jobs |
| Distance to assignment: remaining route and blocks to the assigned emergency | ✓ | ✓ | |
| Time to complete: ETA to the scene, minutes until the job is done, on-scene progress rings, wait times | ✓ | ✓ | wait and drive bars per call |
| Trails: the last 45 minutes of driving | ✓ | ✓ | |
| Coverage heatmap: drive time to the nearest vehicle | ✓ | (it's the terrain) | |
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
