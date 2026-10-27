export interface GifFrame { time: number; delay: number }
interface RunTiming {
  calls: { time: number }[]
  vehicles: { segments: { start: number; end: number }[] }[]
}

/** GIF delays use 10ms ticks. Keep every segment, even between regular samples. */
export function planFrames(span: { start: number; end: number }, speed: number, runs: RunTiming[]): GifFrame[] {
  const { start, end } = span
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start
    || !Number.isFinite(speed) || speed <= 0) throw new Error('Invalid GIF speed or run span')
  if (start === end) return [{ time: start, delay: 100 }]
  const times = new Set([start, end])
  const add = (time: number) => { if (Number.isFinite(time) && time >= start && time <= end) times.add(time) }
  const step = speed / 10
  for (let i = 1; start + i * step < end; i++) add(start + i * step)
  for (const run of runs) {
    run.calls.forEach((call) => add(call.time))
    for (const vehicle of run.vehicles) for (const segment of vehicle.segments) {
      add(segment.start)
      add(segment.end)
      // Capture within the segment, since its end belongs to the next segment.
      if (segment.end > segment.start) add((segment.start + segment.end) / 2)
    }
  }
  const sorted = [...times].sort((a, b) => a - b)
  const ticks = Math.max(1, Math.round((end - start) / speed * 100))
  // Browsers often clamp 10ms GIF frames to 100ms. Use at least 20ms.
  const minimumTicks = 2
  if ((sorted.length - 1) * minimumTicks > ticks) {
    throw new Error('This speed is too fast to show every segment in a GIF. Select a slower playback speed.')
  }
  let previous = 0
  const frames: GifFrame[] = []
  for (let i = 0; i < sorted.length - 1; i++) {
    const desired = Math.round((sorted[i + 1] - start) / (end - start) * ticks)
    const next = Math.max(previous + minimumTicks, Math.min(desired, ticks - (sorted.length - 2 - i) * minimumTicks))
    frames.push({ time: sorted[i], delay: (next - previous) * 10 })
    previous = next
  }
  frames.push({ time: end, delay: 100 })
  return frames
}
