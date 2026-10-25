import type { Segment, SegmentKind, Trace, TraceCall, XY } from '@/contract/trace'
import type { CallStatus } from './status'

/** Per-call timeline derived from the vehicle segments. */
export interface CallTimeline {
  call: TraceCall
  vehicle?: number
  dispatch?: number
  arrive?: number
  finish?: number
}

export interface Bounds {
  minX: number
  maxX: number
  minY: number
  maxY: number
}

export interface Prepared {
  trace: Trace
  calls: CallTimeline[]
  callById: Map<number, CallTimeline>
  bounds: Bounds
  /** Per-minute series starting at span.start, for the scrubber sparkline. */
  busySeries: number[]
  waitingSeries: number[]
}

export interface VehicleFrame {
  id: number
  x: number
  y: number
  status: SegmentKind
  segment?: Segment
  call?: TraceCall
  /** Current position followed by the corners still to drive in this segment. */
  remainingPath: XY[]
  blocksToTarget: number
  target?: XY
  minutesToArrive?: number
  /** Minutes until the vehicle's current job is finished (driving + working). */
  minutesToComplete?: number
  /** 0..1 through the current segment. */
  progress: number
}

export interface CallFrame {
  call: TraceCall
  status: CallStatus
  vehicle?: number
  /** Minutes since the call came in, until a vehicle arrived (or now, if still waiting). */
  waited: number
  /** 0..1 through the on-scene work. */
  progress: number
}

export interface Frame {
  t: number
  vehicles: VehicleFrame[]
  calls: CallFrame[]
  stats: { waiting: number; enRoute: number; onScene: number; done: number; busy: number; avgResponse: number | null }
}

// ---------- geometry ----------

export const manhattan = (a: XY, b: XY) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1])

export function pathLength(path: XY[]): number {
  let d = 0
  for (let i = 1; i < path.length; i++) d += manhattan(path[i - 1], path[i])
  return d
}

/** Point `d` blocks along the path, plus the index of the leg it's on. */
export function pointAlong(path: XY[], d: number): { p: XY; leg: number } {
  for (let i = 1; i < path.length; i++) {
    const [a, b] = [path[i - 1], path[i]]
    const leg = manhattan(a, b)
    if (d <= leg) {
      const f = leg === 0 ? 0 : d / leg
      return { p: [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f], leg: i }
    }
    d -= leg
  }
  return { p: path[path.length - 1], leg: path.length }
}

/** The part of a path between d0 and d1 blocks from its start. */
export function subPath(path: XY[], d0: number, d1: number): XY[] {
  const a = pointAlong(path, d0)
  const b = pointAlong(path, d1)
  return [a.p, ...path.slice(a.leg, b.leg), b.p]
}

// ---------- preparation (memoised per trace) ----------

const cache = new WeakMap<Trace, Prepared>()

export function prepare(trace: Trace): Prepared {
  const hit = cache.get(trace)
  if (hit) return hit

  const calls: CallTimeline[] = trace.calls.map((call) => ({ call }))
  const callById = new Map(calls.map((c) => [c.call.id, c]))
  for (const v of trace.vehicles) {
    for (const s of v.segments) {
      const c = s.callId === undefined ? undefined : callById.get(s.callId)
      if (!c) continue
      c.vehicle = v.id
      if (s.kind === 'to_job') {
        c.dispatch = s.start
        c.arrive = s.end
      } else if (s.kind === 'on_job') {
        c.arrive ??= s.start
        c.finish = s.end
      }
    }
  }

  const pts: XY[] = [[0, 0], ...trace.calls.map((c) => [c.x, c.y] as XY)]
  for (const v of trace.vehicles) for (const s of v.segments) pts.push(...s.path)
  const pad = 2
  const bounds = {
    minX: Math.min(...pts.map((p) => p[0])) - pad,
    maxX: Math.max(...pts.map((p) => p[0])) + pad,
    minY: Math.min(...pts.map((p) => p[1])) - pad,
    maxY: Math.max(...pts.map((p) => p[1])) + pad,
  }

  const { start, end } = trace.span
  const n = Math.max(1, Math.ceil(end - start) + 1)
  const busy = new Array(n + 1).fill(0)
  const waiting = new Array(n + 1).fill(0)
  const bump = (arr: number[], from: number, to: number) => {
    const a = Math.max(0, Math.floor(from - start))
    const b = Math.max(a, Math.min(n, Math.ceil(to - start)))
    arr[a] += 1
    arr[b] -= 1
  }
  for (const v of trace.vehicles) for (const s of v.segments) if (s.kind !== 'idle' && s.end > s.start) bump(busy, s.start, s.end)
  for (const c of calls) bump(waiting, c.call.time, c.dispatch ?? end)
  const acc = (arr: number[]) => {
    let run = 0
    return arr.slice(0, n).map((x) => (run += x))
  }

  const prepared = { trace, calls, callById, bounds, busySeries: acc(busy), waitingSeries: acc(waiting) }
  cache.set(trace, prepared)
  return prepared
}

// ---------- sampling ----------

/** Index of the last segment starting at or before t (segments are in time order). */
function segmentIndex(segments: Segment[], t: number): number {
  let lo = 0
  let hi = segments.length - 1
  let ans = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (segments[mid].start <= t) {
      ans = mid
      lo = mid + 1
    } else hi = mid - 1
  }
  return ans
}

const MOVING: SegmentKind[] = ['to_job', 'to_base', 'reposition']

export function sampleVehicle(p: Prepared, vehicleIndex: number, t: number): VehicleFrame {
  const v = p.trace.vehicles[vehicleIndex]
  const i = segmentIndex(v.segments, t)
  const idle = (xy: XY): VehicleFrame => ({
    id: v.id, x: xy[0], y: xy[1], status: 'idle', remainingPath: [xy], blocksToTarget: 0, progress: 0,
  })
  if (i < 0) return idle([0, 0])

  const s = v.segments[i]
  const call = s.callId === undefined ? undefined : p.callById.get(s.callId)?.call
  if (t >= s.end && !(s.start === s.end && t === s.start && s.kind !== 'to_base')) {
    // Between segments: parked wherever the last one ended.
    const at = pointAlong(s.path, s.end - s.start).p
    return idle(at)
  }

  const elapsed = t - s.start
  const length = pathLength(s.path)
  const here = pointAlong(s.path, Math.min(elapsed, length))
  const frame: VehicleFrame = {
    id: v.id,
    x: here.p[0],
    y: here.p[1],
    status: s.kind,
    segment: s,
    call,
    remainingPath: [here.p, ...s.path.slice(here.leg)],
    blocksToTarget: MOVING.includes(s.kind) ? Math.max(0, length - elapsed) : 0,
    target: s.path[s.path.length - 1],
    progress: s.end > s.start ? (t - s.start) / (s.end - s.start) : 1,
  }
  if (MOVING.includes(s.kind)) frame.minutesToArrive = s.end - t
  if (s.kind === 'to_job' && call) frame.minutesToComplete = s.end - t + call.duration
  if (s.kind === 'on_job') frame.minutesToComplete = s.end - t
  return frame
}

export function sampleFrame(p: Prepared, t: number): Frame {
  const vehicles = p.trace.vehicles.map((_, i) => sampleVehicle(p, i, t))
  const stats = { waiting: 0, enRoute: 0, onScene: 0, done: 0, busy: 0, avgResponse: null as number | null }
  let responseSum = 0
  let responded = 0
  const calls: CallFrame[] = p.calls.map((c) => {
    let status: CallStatus
    if (t < c.call.time) status = 'future'
    else if (c.dispatch === undefined || t < c.dispatch) status = 'waiting'
    else if (c.arrive === undefined || t < c.arrive) status = 'dispatched'
    else if (c.finish === undefined || t < c.finish || (c.finish === c.arrive && t === c.arrive)) status = 'on_scene'
    else status = 'done'
    if (status === 'waiting') stats.waiting++
    if (status === 'dispatched') stats.enRoute++
    if (status === 'on_scene') stats.onScene++
    if (status === 'done') stats.done++
    if (c.arrive !== undefined && t >= c.arrive) {
      responseSum += c.arrive - c.call.time
      responded++
    }
    const waited = Math.max(0, Math.min(t, c.arrive ?? t) - c.call.time)
    const progress =
      status === 'on_scene' && c.arrive !== undefined && c.finish !== undefined && c.finish > c.arrive
        ? (t - c.arrive) / (c.finish - c.arrive)
        : status === 'done' ? 1 : 0
    return { call: c.call, status, vehicle: c.vehicle, waited, progress }
  })
  stats.busy = vehicles.filter((v) => v.status !== 'idle').length
  stats.avgResponse = responded ? responseSum / responded : null
  return { t, vehicles, calls, stats }
}

/** The path a vehicle drove during [t - window, t], for trails. */
export function trail(p: Prepared, vehicleIndex: number, t: number, window: number): XY[] {
  const out: XY[] = []
  for (const s of p.trace.vehicles[vehicleIndex].segments) {
    if (s.end < t - window || s.start > t || s.path.length < 2) continue
    const len = pathLength(s.path)
    const d0 = Math.max(0, t - window - s.start)
    const d1 = Math.min(len, t - s.start, s.end - s.start)
    if (d1 > d0) out.push(...subPath(s.path, d0, d1))
  }
  return out
}

/** Manhattan distance from (x, y) to the nearest of `points`. */
export function nearestDistance(x: number, y: number, points: XY[]): number {
  let best = Infinity
  for (const q of points) {
    const d = Math.abs(x - q[0]) + Math.abs(y - q[1])
    if (d < best) best = d
  }
  return best
}
