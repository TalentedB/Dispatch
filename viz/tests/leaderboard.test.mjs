import assert from 'node:assert/strict'
import { test } from 'node:test'
import { standings, totalEmergencyWait } from '../src/engine/leaderboard.ts'

function trace(waits) {
  return {
    check: { valid: true },
    calls: waits.map((_, id) => ({ id, time: id * 100, duration: 1 })),
    vehicles: [{ segments: waits.map((wait, id) => ({
      kind: 'on_job', callId: id, start: id * 100 + wait, end: id * 100 + wait + 1,
    })) }],
    metrics: { avg_response: 999 },
  }
}

test('total wait sums actual call delays rather than rounded averages or service durations', () => {
  assert.equal(totalEmergencyWait(trace([2, 7, 0])), 9)
  assert.equal(totalEmergencyWait(trace([])), 0)
})

test('lowest combined wait wins even when another algorithm wins more scenarios', () => {
  const scenarios = ['one', 'two', 'three'].map((id) => ({ id, algorithms: ['a', 'b'] }))
  const traces = {
    one: { a: trace([1]), b: trace([2]) },
    two: { a: trace([1]), b: trace([2]) },
    three: { a: trace([100]), b: trace([3]) },
  }
  const { list } = standings(scenarios, traces, 'total_wait')
  assert.deepEqual(list.map((entry) => [entry.algo, entry.total]), [['b', 7], ['a', 102]])
  assert.equal(list[1].wins, 2)
})

test('missing, invalid, or unserved emergencies cannot win with an artificially small total', () => {
  const scenarios = [{ id: 'one', algorithms: ['valid', 'missing', 'invalid', 'unserved'] }]
  const unserved = trace([0])
  unserved.vehicles = []
  const invalid = trace([0])
  invalid.check.valid = false
  const { list } = standings(scenarios, { one: { valid: trace([10]), invalid, unserved } }, 'total_wait')
  assert.equal(list[0].algo, 'valid')
  assert.ok(list.slice(1).every((entry) => entry.total === Infinity && entry.invalid === 1))
})

test('equal wait totals have stable ordering and duplicate or early service is rejected', () => {
  assert.equal(totalEmergencyWait(trace([-1])), Infinity)
  const duplicate = trace([2])
  duplicate.vehicles[0].segments.push(duplicate.vehicles[0].segments[0])
  assert.equal(totalEmergencyWait(duplicate), Infinity)
  const { list } = standings([{ id: 'one', algorithms: ['b', 'a'] }],
    { one: { a: trace([2]), b: trace([2]) } }, 'total_wait')
  assert.deepEqual(list.map((entry) => entry.algo), ['a', 'b'])
})
