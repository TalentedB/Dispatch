import { useId } from 'react'
import { ShieldCheck } from 'lucide-react'
import { themeColor } from '@/lib/theme'
import type { Bounds, Frame } from '@/engine/sample'
import type { OverlayPlugin } from './types'

/**
 * Drive time each vehicle covers. Chosen so the fleet, spread perfectly,
 * would exactly blanket the service area: N diamonds of area 2R² = W·H.
 * So it grows with the city and shrinks as the fleet grows.
 */
export function coverageRadius(bounds: Bounds, fleet: number): number {
  const area = (bounds.maxX - bounds.minX) * (bounds.maxY - bounds.minY)
  return Math.max(1, Math.round(Math.sqrt(area / (2 * Math.max(1, fleet)))))
}

/** Share of intersections in the service area within the coverage radius of a vehicle. */
export function coveredShare(bounds: Bounds, frame: Frame): number {
  const r = coverageRadius(bounds, frame.vehicles.length)
  const pts = frame.vehicles
  let covered = 0
  let total = 0
  for (let x = bounds.minX; x <= bounds.maxX; x++) {
    for (let y = bounds.minY; y <= bounds.maxY; y++) {
      total++
      if (pts.some((v) => Math.abs(v.x - x) + Math.abs(v.y - y) <= r)) covered++
    }
  }
  return total ? covered / total : 0
}

function Zones({ bounds, frame, sy }: { bounds: Bounds; frame: Frame; sy: (y: number) => number }) {
  const clip = useId()
  const r = coverageRadius(bounds, frame.vehicles.length)
  const { minX, maxX, minY, maxY } = bounds
  return (
    <g style={{ pointerEvents: 'none' }}>
      <clipPath id={clip}>
        <rect x={minX} y={sy(maxY)} width={maxX - minX} height={maxY - minY} />
      </clipPath>
      {/* Opaque shapes inside a translucent group, so overlapping zones don't get darker. */}
      <g clipPath={`url(#${clip})`} opacity={0.32}>
        {frame.vehicles.map((v) => (
          <polygon key={v.id} fill={themeColor('coverage-near')}
            points={`${v.x},${sy(v.y + r)} ${v.x + r},${sy(v.y)} ${v.x},${sy(v.y - r)} ${v.x - r},${sy(v.y)}`} />
        ))}
      </g>
    </g>
  )
}

export const zonesOverlay: OverlayPlugin = {
  id: 'zones',
  label: 'Coverage zones',
  description: 'Area around each vehicle it can reach quickly. The reach is sized so the whole fleet, spread out, would just cover the city.',
  icon: ShieldCheck,
  defaultOn: true,
  under: true,
  render: { map2d: ({ prepared, frame, sy }) => <Zones bounds={prepared.bounds} frame={frame} sy={sy} /> },
}
