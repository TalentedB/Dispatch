import type { Bounds, Frame } from './sample.ts'
import { nearestResponseTime, responseReadiness } from './sample.ts'

/**
 * Drive time each vehicle covers. Chosen so the fleet, spread perfectly,
 * would exactly blanket the service area: N diamonds of area 2R² = W·H.
 * So it grows with the city and shrinks as the fleet grows.
 */
export function coverageRadius(bounds: Bounds, fleet: number): number {
  const area = (bounds.maxX - bounds.minX) * (bounds.maxY - bounds.minY)
  return Math.max(1, Math.round(Math.sqrt(area / (2 * Math.max(1, fleet)))))
}

/** Share of intersections reachable within the response threshold, including busy time. */
export function coveredShare(bounds: Bounds, frame: Frame): number {
  const r = coverageRadius(bounds, frame.vehicles.length)
  let covered = 0
  let total = 0
  for (let x = bounds.minX; x <= bounds.maxX; x++) {
    for (let y = bounds.minY; y <= bounds.maxY; y++) {
      total++
      if (nearestResponseTime(x, y, frame.vehicles) <= r) covered++
    }
  }
  return total ? covered / total : 0
}

export function responseCoverageZones(bounds: Bounds, frame: Frame) {
  const responseBudget = coverageRadius(bounds, frame.vehicles.length)
  return frame.vehicles.flatMap((vehicle) => {
    const ready = responseReadiness(vehicle)
    const radius = responseBudget - ready.waitMinutes
    return radius < 0 ? [] : [{ vehicle: vehicle.id, x: ready.x, y: ready.y, radius }]
  })
}

