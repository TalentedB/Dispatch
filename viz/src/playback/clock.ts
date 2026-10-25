import { useEffect } from 'react'
import { createStore } from '@/lib/store'

/** One shared clock drives every pane, so side-by-side views stay in sync. */
export const SPEEDS = [1, 2, 5, 10, 20, 30, 60, 120] // simulated minutes per real second

interface ClockState {
  time: number
  playing: boolean
  speed: number
  span: { start: number; end: number }
}

export const clock = createStore<ClockState>({
  time: 0,
  playing: false,
  speed: 10,
  span: { start: 0, end: 1440 },
})

const clamp = (t: number) => {
  const { start, end } = clock.get().span
  return Math.min(end, Math.max(start, t))
}

export const clockActions = {
  seek: (t: number) => clock.set({ time: clamp(t) }),
  step: (minutes: number) => clock.set((s) => ({ time: clamp(Math.round(s.time) + minutes), playing: false })),
  toggle: () =>
    clock.set((s) => (s.time >= s.span.end ? { playing: true, time: s.span.start } : { playing: !s.playing })),
  setSpeed: (speed: number) => clock.set({ speed }),
  faster: () => clock.set((s) => ({ speed: SPEEDS[Math.min(SPEEDS.length - 1, SPEEDS.indexOf(s.speed) + 1)] })),
  slower: () => clock.set((s) => ({ speed: SPEEDS[Math.max(0, SPEEDS.indexOf(s.speed) - 1)] })),
  setSpan: (span: { start: number; end: number }) =>
    clock.set((s) => ({ span, time: s.time < span.start || s.time > span.end ? span.start : s.time })),
}

/** Advances the clock with requestAnimationFrame while playing. Mount once. */
export function useClockDriver() {
  useEffect(() => {
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000)
      last = now
      const s = clock.get()
      if (s.playing) {
        const time = s.time + dt * s.speed
        if (time >= s.span.end) clock.set({ time: s.span.end, playing: false })
        else clock.set({ time })
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [])
}

export function formatClock(t: number, seconds = false): string {
  const day = Math.floor(t / 1440)
  const m = ((t % 1440) + 1440) % 1440
  const hh = String(Math.floor(m / 60)).padStart(2, '0')
  const mm = String(Math.floor(m % 60)).padStart(2, '0')
  const ss = seconds ? `:${String(Math.floor((m % 1) * 60)).padStart(2, '0')}` : ''
  return `${hh}:${mm}${ss}${day > 0 ? ` +${day}d` : ''}`
}

export function formatMinutes(m: number, compact = false): string {
  if (!compact && m < 1) return '<1 min'
  const r = Math.ceil(m)
  const h = Math.floor(r / 60)
  if (compact) return h ? `${h}h${String(r % 60).padStart(2, '0')}` : `${r}m`
  return h ? `${h}h ${r % 60}m` : `${r} min`
}
