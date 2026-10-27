import { test } from 'node:test'
import assert from 'node:assert/strict'
import { planFrames } from '../src/export/timing.ts'

test('GIF length follows playback speed across the whole run', () => {
  const frames = planFrames({ start: 12, end: 1012 }, 10, [])
  assert.equal(frames[0].time, 12)
  assert.equal(frames.at(-1).time, 1012)
  assert.equal(frames.reduce((sum, f) => sum + f.delay, 0), 100000 + 100)
  const faster = planFrames({ start: 12, end: 1012 }, 20, [])
  assert.equal(faster.reduce((sum, f) => sum + f.delay, 0), 50000 + 100)
})

test('stationary runs have one frame and invalid spans are rejected', () => {
  assert.deepEqual(planFrames({ start: 5, end: 5 }, 10, []), [{ time: 5, delay: 100 }])
  assert.throws(() => planFrames({ start: 6, end: 5 }, 10, []))
  assert.throws(() => planFrames({ start: 0, end: Infinity }, 10, []))
  assert.throws(() => planFrames({ start: 0, end: 10 }, 0, []))
})

test('short segments between regular frames appear in the GIF', () => {
  const trace = { calls: [{ time: 2.1 }], vehicles: [{ segments: [
    { start: 2.1, end: 2.2 }, { start: 2.2, end: 2.4 },
  ] }] }
  const frames = planFrames({ start: 0, end: 100 }, 20, [trace])
  for (const segment of trace.vehicles[0].segments) {
    assert.ok(frames.some((f) => f.time > segment.start && f.time < segment.end))
  }
  assert.ok(frames.some((f) => f.time === 2.1))
  assert.equal(frames.reduce((sum, f) => sum + f.delay, 0), 5100)
  assert.ok(frames.every((f) => f.delay >= 20 && f.delay % 10 === 0))
})

test('reports speeds that cannot represent all segments instead of dropping them', () => {
  assert.throws(() => planFrames({ start: 0, end: 0.1 }, 120, []), /slower playback speed/)
})
