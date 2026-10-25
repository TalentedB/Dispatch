import { themeColor } from '@/lib/theme'
/** Drive-time colour ramp: 0 = near a vehicle (sage), 1+ = far away (clay). */
const rgb = (role: string): [number, number, number] => {
  const hex = themeColor(role).slice(1)
  return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number]
}
const STOPS: [number, [number, number, number]][] = [
  [0, rgb('coverage-near')], [0.5, rgb('coverage-mid')], [1, rgb('coverage-far')],
]

export function distanceColor(f: number): [number, number, number] {
  const x = Math.max(0, Math.min(1, f))
  for (let i = 1; i < STOPS.length; i++) {
    const [b, cb] = STOPS[i]
    const [a, ca] = STOPS[i - 1]
    if (x <= b) {
      const k = (x - a) / (b - a)
      return [0, 1, 2].map((j) => Math.round(ca[j] + (cb[j] - ca[j]) * k)) as [number, number, number]
    }
  }
  return STOPS[STOPS.length - 1][1]
}
