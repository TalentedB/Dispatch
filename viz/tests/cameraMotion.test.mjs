import assert from 'node:assert/strict'
import { test } from 'node:test'
import { animateCamera, CAMERA_TRANSITION_MS } from '../src/views/cameraMotion.ts'

function animationClock(context) {
  const frames = new Map()
  let nextId = 0
  context.mock.method(performance, 'now', () => 0)
  globalThis.requestAnimationFrame = (callback) => {
    frames.set(++nextId, callback)
    return nextId
  }
  globalThis.cancelAnimationFrame = (id) => frames.delete(id)
  context.after(() => {
    delete globalThis.requestAnimationFrame
    delete globalThis.cancelAnimationFrame
  })
  return {
    frames,
    advance(time) {
      const pending = [...frames.values()]
      frames.clear()
      pending.forEach((callback) => callback(time))
    },
  }
}

test('expansion zoom progresses through intermediate scales and finishes exactly', (context) => {
  const clock = animationClock(context)
  const samples = []
  animateCamera([10, 3, -3], [2, 0, 0], (pose) => samples.push(pose), false)
  assert.equal(samples.length, 0)
  clock.advance(0)
  assert.deepEqual(samples[0], [10, 3, -3])
  clock.advance(CAMERA_TRANSITION_MS / 2)
  assert.ok(samples[1][0] > 2 && samples[1][0] < 10)
  assert.ok(samples[1][1] > 0 && samples[1][1] < 3)
  clock.advance(CAMERA_TRANSITION_MS)
  assert.deepEqual(samples.at(-1), [2, 0, 0])
  assert.equal(clock.frames.size, 0)
})

test('manual input can cancel a zoom without a later camera jump', (context) => {
  const clock = animationClock(context)
  const samples = []
  const cancel = animateCamera([10], [2], (pose) => samples.push(pose), false)
  clock.advance(100)
  cancel()
  const count = samples.length
  clock.advance(1000)
  assert.equal(samples.length, count)
  assert.equal(clock.frames.size, 0)
})

test('another expansion starts from the currently visible camera pose', (context) => {
  const clock = animationClock(context)
  let visible = [10]
  const update = (pose) => { visible = pose }
  const cancel = animateCamera(visible, [5], update, false)
  clock.advance(100)
  const interruptedPose = visible
  cancel()
  animateCamera(visible, [2], update, false)
  clock.advance(0)
  assert.deepEqual(visible, interruptedPose)
  clock.advance(CAMERA_TRANSITION_MS)
  assert.deepEqual(visible, [2])
})

test('reduced motion updates the camera immediately without scheduling movement', (context) => {
  const clock = animationClock(context)
  let visible
  animateCamera([10], [2], (pose) => { visible = pose }, true)
  assert.deepEqual(visible, [2])
  assert.equal(clock.frames.size, 0)
})
