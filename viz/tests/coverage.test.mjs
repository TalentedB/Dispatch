import assert from 'node:assert/strict'
import { test } from 'node:test'
import { coveredShare, responseCoverageZones } from '../src/engine/coverage.ts'

test('busy time consumes coverage distance instead of counting an occupied ambulance as free', () => {
  const bounds = { minX: -2, maxX: 2, minY: -2, maxY: 2 }
  // One vehicle gives a three-minute response threshold on this grid.
  const vehicle = { id: 0, x: 0, y: 0, status: 'on_job', progress: 0,
    readyPosition: [0, 0], busyMinutes: 2 }
  assert.equal(coveredShare(bounds, { vehicles: [vehicle] }), 5 / 25)
  assert.equal(coveredShare(bounds, { vehicles: [{ ...vehicle, busyMinutes: 4 }] }), 0)
  assert.equal(coveredShare(bounds, { vehicles: [{ ...vehicle, busyMinutes: 0 }] }), 21 / 25)
})

test('coverage diamonds use the ready location and shrink as remaining work consumes the budget', () => {
  const bounds = { minX: -20, maxX: 20, minY: -20, maxY: 20 }
  const free = { id: 0, x: 0, y: 0, status: 'reposition', progress: 0 }
  const busy = { id: 1, x: 1, y: 0, status: 'to_job', progress: 0,
    readyPosition: [10, 0], busyMinutes: 12 }
  const zones = (minutes) => responseCoverageZones(bounds,
    { vehicles: [free, { ...busy, busyMinutes: minutes }] })
  assert.deepEqual(zones(12), [
    { vehicle: 0, x: 0, y: 0, radius: 20 },
    { vehicle: 1, x: 10, y: 0, radius: 8 },
  ])
  assert.equal(zones(11)[1].radius, 9)
  assert.equal(zones(21).length, 1)
  assert.deepEqual(zones(0)[1], { vehicle: 1, x: 10, y: 0, radius: 20 })
})
