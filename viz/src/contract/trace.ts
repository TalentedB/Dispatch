/**
 * The trace contract: everything the visualizer needs from one algorithm run on one scenario.
 *
 * Any algorithm can connect to the frontend by producing this JSON. Two ways:
 *   1. Print the brief's text schedule and register the solver in solvers.txt;
 *      `python3 tools/export_viz.py` replays it into a trace (kinds to_job/on_job/to_base).
 *   2. Emit a trace directly (any language) and drop the file onto the app. This is the
 *      route for states the text format can't express, e.g. `reposition` or `idle` away from base.
 *
 * Coordinates are grid blocks relative to the base at (0, 0): +x east, +y north.
 * Times are absolute minutes since midnight of day 0 (may exceed 1440 past midnight).
 */

export const TRACE_SCHEMA = 'uvec.trace/v1'

export type XY = [number, number]

/** What a vehicle is doing during a segment. Add new kinds in engine/status.ts. */
export type SegmentKind = 'to_job' | 'on_job' | 'to_base' | 'reposition' | 'idle'

export interface Segment {
  kind: SegmentKind
  start: number
  end: number
  /** Grid corners in driving order. Stationary segments have one point. Speed is 1 block/min. */
  path: XY[]
  /** The call being served (to_job / on_job). */
  callId?: number
  /** A drive cut short (e.g. a return to base redirected to a new job). */
  interrupted?: boolean
}

export interface TraceVehicle {
  id: number
  segments: Segment[]
}

export interface TraceCall {
  id: number
  time: number
  x: number
  y: number
  duration: number
}

export interface TraceLogLine {
  time: number
  vehicle: number
  text: string
}

export interface Trace {
  schema: typeof TRACE_SCHEMA
  algorithm: { id: string; label?: string; description?: string }
  scenario: { id: string; label?: string; group?: string | null; vehicles: number }
  calls: TraceCall[]
  vehicles: TraceVehicle[]
  span: { start: number; end: number }
  /** Validity verdict from tester/checker.py (optional for hand-made traces). */
  check?: { valid: boolean; errors: string[] }
  /** Scores from tester/checker.py. Unknown keys are shown as-is. */
  metrics?: Record<string, number> | null
  /** The raw printed schedule, for the event log. */
  log?: TraceLogLine[]
  /** Optional native dispatch diagnostics. Proof applies to a replan, not the full online day. */
  dispatch?: {
    mapHistory: { time: number; bounds: [number, number, number, number] }[]
    coverage?: { time: number; busyAnchors: { vehicle: number; x: number; y: number; available: number }[] }[]
    plans: {
      algorithm: string
      status: string
      primaryOptimal: boolean
      lexicographicOptimal: boolean
      gap: number | null
      seconds: number
      fallbackReason: string | null
    }[]
  }
}

export interface ManifestScenario {
  id: string
  label: string
  group: string
  vehicles: number
  calls: number
  traces: Record<string, string>
}

export interface Manifest {
  schema: string
  algorithms: string[]
  scenarios: ManifestScenario[]
}

/** Throws a readable error if `data` doesn't look like a trace. */
export function validateTrace(data: unknown): Trace {
  const t = data as Trace
  const fail = (msg: string): never => {
    throw new Error(`Not a valid ${TRACE_SCHEMA} trace: ${msg}`)
  }
  if (!t || typeof t !== 'object') fail('not an object')
  if (t.schema !== TRACE_SCHEMA) fail(`schema is ${JSON.stringify(t.schema)}`)
  if (!t.algorithm?.id) fail('missing algorithm.id')
  if (!t.scenario?.id) fail('missing scenario.id')
  if (!Array.isArray(t.calls)) fail('calls must be an array')
  if (!Array.isArray(t.vehicles)) fail('vehicles must be an array')
  for (const v of t.vehicles) {
    if (!Array.isArray(v.segments)) fail(`vehicle ${v.id} has no segments array`)
    for (const s of v.segments) {
      if (!(s.end >= s.start)) fail(`vehicle ${v.id} has a segment ending before it starts`)
      if (!Array.isArray(s.path) || s.path.length === 0) fail(`vehicle ${v.id} has a segment with no path`)
    }
  }
  if (!t.span) {
    const times = [...t.calls.map((c) => c.time), ...t.vehicles.flatMap((v) => v.segments.map((s) => s.end))]
    t.span = { start: Math.min(...times) - 5, end: Math.max(...times) + 5 }
  }
  t.scenario.vehicles ??= t.vehicles.length
  return t
}
