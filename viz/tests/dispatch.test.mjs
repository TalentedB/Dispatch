import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { prepare, sampleFrame, sampleVehicle, pointAlong, nearestResponseTime } from '../src/engine/sample.ts'
import { validateTrace } from '../src/contract/trace.ts'

const tracesRoot = new URL('../public/traces/', import.meta.url)
const manifest = JSON.parse(readFileSync(new URL('manifest.json', tracesRoot), 'utf8'))
const dispatchAlgorithms = new Set(['strategy4', 'milp', 'dispatch_greedy'])
const nativeTraces = manifest.scenarios.flatMap((scenario) =>
  Object.entries(scenario.traces)
    .filter(([algorithm]) => dispatchAlgorithms.has(algorithm))
    .map(([, path]) => JSON.parse(readFileSync(new URL(path, tracesRoot), 'utf8'))),
)

test('coverage response adds locked travel/service time from the eventual ready location', () => {
  const trace = validateTrace({
    schema: 'uvec.trace/v1', algorithm: { id: 'availability' },
    scenario: { id: 'availability', vehicles: 2 },
    calls: [{ id: 0, time: 0, x: -4, y: 0, duration: 10 }],
    vehicles: [
      { id: 0, segments: [
        { kind: 'to_job', start: 0, end: 4, path: [[0, 0], [-4, 0]], callId: 0 },
        { kind: 'on_job', start: 4, end: 14, path: [[-4, 0]], callId: 0 },
      ] },
      { id: 1, segments: [
        { kind: 'reposition', start: 0, end: 4, path: [[0, 0], [4, 0]] },
      ] },
    ], span: { start: 0, end: 20 },
  })
  const prepared = prepare(trace)
  // At t=2 the locked ambulance is only two blocks away, but cannot switch jobs.
  assert.equal(nearestResponseTime(-4, 0, sampleFrame(prepared, 2).vehicles), 6)
  assert.equal(nearestResponseTime(-4, 0, sampleFrame(prepared, 5).vehicles), 8)
  assert.equal(nearestResponseTime(-4, 0, sampleFrame(prepared, 12).vehicles), 2)
  assert.equal(nearestResponseTime(-4, 0, sampleFrame(prepared, 14).vehicles), 0)
})

test('native readiness forecasts include known queues without reading future snapshots', () => {
  const trace = validateTrace({
    schema: 'uvec.trace/v1', algorithm: { id: 'queued-availability' },
    scenario: { id: 'queued-availability', vehicles: 1 },
    calls: [
      { id: 0, time: 0, x: -4, y: 0, duration: 10 },
      { id: 1, time: 10, x: -8, y: 0, duration: 12 },
    ],
    vehicles: [{ id: 0, segments: [
      { kind: 'to_job', start: 0, end: 4, path: [[0, 0], [-4, 0]], callId: 0 },
      { kind: 'on_job', start: 4, end: 14, path: [[-4, 0]], callId: 0 },
      { kind: 'to_job', start: 14, end: 18, path: [[-4, 0], [-8, 0]], callId: 1 },
      { kind: 'on_job', start: 18, end: 30, path: [[-8, 0]], callId: 1 },
    ] }], span: { start: 0, end: 35 },
    dispatch: { mapHistory: [], plans: [], coverage: [
      { time: 0, busyAnchors: [{ vehicle: 0, x: -4, y: 0, available: 14 }] },
      { time: 10, busyAnchors: [{ vehicle: 0, x: -8, y: 0, available: 30 }] },
    ] },
  })
  const prepared = prepare(trace)
  const earlier = sampleVehicle(prepared, 0, 5)
  assert.deepEqual(earlier.readyPosition, [-4, 0])
  assert.equal(earlier.busyMinutes, 9)
  const queued = sampleVehicle(prepared, 0, 12)
  assert.deepEqual(queued.readyPosition, [-8, 0])
  assert.equal(queued.busyMinutes, 18)
  assert.equal(nearestResponseTime(-8, 0, [queued]), 18)
})

test('map bounds use only reported calls and expand symmetrically around the origin', () => {
  const trace = validateTrace({
    schema: 'uvec.trace/v1',
    algorithm: { id: 'bounds-regression' },
    scenario: { id: 'bounds-regression', vehicles: 1 },
    calls: [
      { id: 0, time: 10, x: 7, y: 0, duration: 0 },
      { id: 1, time: 20, x: 0, y: -30, duration: 0 },
    ],
    vehicles: [{ id: 0, segments: [] }],
    span: { start: 0, end: 30 },
  })
  const prepared = prepare(trace)
  assert.deepEqual(sampleFrame(prepared, 0).bounds, { minX: -5, maxX: 5, minY: -5, maxY: 5 })
  assert.deepEqual(sampleFrame(prepared, 10).bounds, { minX: -7, maxX: 7, minY: -7, maxY: 7 })
  assert.deepEqual(sampleFrame(prepared, 19).bounds, { minX: -7, maxX: 7, minY: -7, maxY: 7 })
  assert.deepEqual(sampleFrame(prepared, 20).bounds, { minX: -30, maxX: 30, minY: -30, maxY: 30 })
  assert.deepEqual(sampleFrame(prepared, 0).bounds, { minX: -5, maxX: 5, minY: -5, maxY: 5 })
})

test('configured initial bounds ignore future map history and movement destinations', () => {
  const trace = validateTrace({
    schema: 'uvec.trace/v1',
    algorithm: { id: 'bounds-regression' },
    scenario: { id: 'custom-initial-extent', vehicles: 1 },
    calls: [{ id: 0, time: 100, x: 30, y: 0, duration: 0 }],
    vehicles: [{ id: 0, segments: [
      { kind: 'to_job', start: 100, end: 130, path: [[0, 0], [30, 0]], callId: 0 },
    ] }],
    span: { start: 0, end: 150 },
    dispatch: {
      mapHistory: [{ time: 0, bounds: [-2, 2, -2, 2] }, { time: 100, bounds: [-30, 30, -30, 30] }],
      plans: [],
    },
  })
  const prepared = prepare(trace)
  assert.deepEqual(sampleFrame(prepared, 99).bounds, { minX: -2, maxX: 2, minY: -2, maxY: 2 })
  assert.deepEqual(sampleFrame(prepared, 100).bounds, { minX: -30, maxX: 30, minY: -30, maxY: 30 })
})

test('the bundled frontend scenarios include Strategy 4', () => {
  assert.ok(manifest.scenarios.every((scenario) => scenario.traces.strategy4))
  assert.ok(nativeTraces.length > 0)
})

for (const trace of nativeTraces) {
  test(`${trace.scenario.id}/${trace.algorithm.id}: playback matches the native schedule`, () => {
    const prepared = prepare(validateTrace(trace))
    assert.equal(trace.check.valid, true)
    const reportedExtents = new Map(trace.dispatch.mapHistory.map((entry) => [entry.time, entry.bounds]))
    for (const [time, [minX, maxX, minY, maxY]] of reportedExtents) {
      assert.deepEqual(sampleFrame(prepared, time).bounds, { minX, maxX, minY, maxY })
      assert.equal(minX, -maxX)
      assert.equal(minY, -maxY)
      assert.equal(maxX, maxY)
    }
    for (const [vehicleIndex, vehicle] of trace.vehicles.entries()) {
      for (const segment of vehicle.segments) {
        if (segment.end === segment.start) continue
        const time = (segment.start + segment.end) / 2
        const frame = sampleVehicle(prepared, vehicleIndex, time)
        const expected = pointAlong(segment.path, time - segment.start).p
        assert.deepEqual([frame.x, frame.y], expected)
        assert.equal(frame.status, segment.kind)
        if (segment.callId !== undefined) assert.equal(frame.call.id, segment.callId)
      }
    }
    const finished = sampleFrame(prepared, trace.span.end)
    assert.equal(finished.stats.done, trace.calls.length)
    assert.equal(finished.stats.busy, 0)
    assert.equal(finished.stats.avgResponse ?? 0, trace.metrics.avg_response)
    if (trace.algorithm.id !== 'strategy4') {
      assert.ok(finished.vehicles.every((vehicle) => vehicle.x === 0 && vehicle.y === 0))
    } else {
      for (const [index, vehicle] of finished.vehicles.entries()) {
        const endpoint = trace.vehicles[index].segments.at(-1)?.path.at(-1) ?? [0, 0]
        assert.deepEqual([vehicle.x, vehicle.y], endpoint)
        assert.ok(trace.vehicles[index].segments.every((segment) => segment.kind !== 'to_base'))
      }
    }
  })
}
