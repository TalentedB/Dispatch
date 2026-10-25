import { useId } from 'react'
import { ShieldCheck } from 'lucide-react'
import { themeColor } from '@/lib/theme'
import type { Bounds, Frame } from '@/engine/sample'
import type { OverlayPlugin } from './types'
import { responseCoverageZones } from '@/engine/coverage'

function Zones({ bounds, frame, sy }: { bounds: Bounds; frame: Frame; sy: (y: number) => number }) {
  const clip = useId()
  const { minX, maxX, minY, maxY } = bounds
  return (
    <g style={{ pointerEvents: 'none' }}>
      <clipPath id={clip}>
        <rect x={minX} y={sy(maxY)} width={maxX - minX} height={maxY - minY} />
      </clipPath>
      {/* Opaque shapes inside a translucent group, so overlapping zones don't get darker. */}
      <g clipPath={`url(#${clip})`} opacity={0.32}>
        {responseCoverageZones(bounds, frame).map(({ vehicle, x, y, radius }) => (
          <polygon key={vehicle} fill={themeColor('coverage-near')}
            points={`${x},${sy(y + radius)} ${x + radius},${sy(y)} ${x},${sy(y - radius)} ${x - radius},${sy(y)}`} />
        ))}
      </g>
    </g>
  )
}

export const zonesOverlay: OverlayPlugin = {
  id: 'zones',
  label: 'Coverage zones',
  description: 'Area reachable within the response threshold. Remaining emergency work consumes the same budget as driving; busy vehicles cover from where they become free.',
  icon: ShieldCheck,
  defaultOn: true,
  under: true,
  render: { map2d: ({ frame, sy }) => <Zones bounds={frame.bounds} frame={frame} sy={sy} /> },
}
