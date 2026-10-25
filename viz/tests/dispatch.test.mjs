import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { prepare, sampleFrame, sampleVehicle, pointAlong } from '../src/engine/sample.ts'
import { validateTrace } from '../src/contract/trace.ts'

const tracesRoot = new URL('../public/traces/', import.meta.url)
const manifest = JSON.parse(readFileSync(new URL('manifest.json', tracesRoot), 'utf8'))
const dispatchAlgorithms = new Set(['strategy4', 'milp', 'dispatch_greedy'])
const nativeTraces = manifest.scenarios.flatMap((scenario) =>
  Object.entries(scenario.traces)
    .filter(([algorithm]) => dispatchAlgorithms.has(algorithm))
    .map(([, path]) => JSON.parse(readFileSync(new URL(path, tracesRoot), 'utf8'))),
)

test('the bundled frontend scenarios include Strategy 4', () => {
  assert.ok(manifest.scenarios.every((scenario) => scenario.traces.strategy4))
  assert.ok(nativeTraces.length > 0)
})

for (const trace of nativeTraces) {
  test(`${trace.scenario.id}/${trace.algorithm.id}: playback matches the native schedule`, () => {
    const prepared = prepare(validateTrace(trace))
    assert.equal(trace.check.valid, true)
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
    assert.ok(finished.vehicles.every((vehicle) => vehicle.x === 0 && vehicle.y === 0))
  })
}
