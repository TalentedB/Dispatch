import type { GifFrame } from './timing.ts'

/** Generate frames without a playback timer or any changes to the live clock. */
export async function captureRun(frames: GifFrame[], capture: (frame: GifFrame) => Promise<void>,
  signal: AbortSignal, progress: (percent: number) => void) {
  for (const [index, frame] of frames.entries()) {
    signal.throwIfAborted()
    await capture(frame)
    signal.throwIfAborted()
    progress(Math.round((index + 1) / frames.length * 100))
  }
}
