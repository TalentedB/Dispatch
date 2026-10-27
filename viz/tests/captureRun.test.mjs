import { test } from 'node:test'
import assert from 'node:assert/strict'
import { captureRun } from '../src/export/captureRun.ts'
import { planFrames } from '../src/export/timing.ts'

test('processes the entire run in order without waiting for its playback duration', async () => {
  const planned = planFrames({ start: 0, end: 100 }, 10, [])
  const captured = []
  const progress = []
  await captureRun(planned, async (frame) => { captured.push(frame) }, new AbortController().signal, (p) => progress.push(p))
  assert.deepEqual(captured, planned)
  assert.equal(progress.at(-1), 100)
  assert.equal(captured.reduce((sum, f) => sum + f.delay, 0), 10100)
})

for (const failure of ['cancel', 'capture failure']) {
  test(`stops processing after ${failure}`, async () => {
    const captured = []
    const abort = new AbortController()
    await assert.rejects(captureRun(planFrames({ start: 0, end: 100 }, 10, []), async (frame) => {
      captured.push(frame)
      if (failure === 'cancel') abort.abort()
      else throw new Error('capture failure')
    }, abort.signal, () => {}))
    assert.equal(captured.length, 1)
  })
}
