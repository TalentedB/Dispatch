/** Drive-time colour ramp: 0 = right next to a vehicle (teal), 1+ = far away (magenta). */
const STOPS: [number, [number, number, number]][] = [
  [0, [20, 184, 166]],
  [0.25, [132, 204, 22]],
  [0.5, [250, 204, 21]],
  [0.75, [249, 115, 22]],
  [1, [225, 29, 72]],
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
