import { useEffect, useRef } from 'react'
import { Radar } from 'lucide-react'
import { nearestDistance } from '@/engine/sample'
import type { XY } from '@/contract/trace'
import { distanceColor } from '@/views/colors'
import type { Map2DContext, OverlayPlugin } from './types'

/** Heatmap of how far the nearest vehicle is from every intersection. */
function CoverageLayer({ prepared, frame, sy }: Map2DContext) {
  const ref = useRef<HTMLCanvasElement>(null)
  const { minX, maxX, minY, maxY } = prepared.bounds
  const w = maxX - minX + 1
  const h = maxY - minY + 1
  useEffect(() => {
    const ctx = ref.current?.getContext('2d')
    if (!ctx) return
    const img = ctx.createImageData(w, h)
    const pts: XY[] = frame.vehicles.map((v) => [v.x, v.y])
    const scale = Math.max(8, (w + h) / 2)
    for (let j = 0; j < h; j++) {
      for (let i = 0; i < w; i++) {
        const d = nearestDistance(minX + i, maxY - j, pts)
        const [r, g, b] = distanceColor(d / scale)
        const k = (j * w + i) * 4
        img.data[k] = r
        img.data[k + 1] = g
        img.data[k + 2] = b
        img.data[k + 3] = 110
      }
    }
    ctx.putImageData(img, 0, 0)
  }, [frame, w, h, minX, maxY])
  return (
    <foreignObject x={minX - 0.5} y={sy(maxY) - 0.5} width={w} height={h} style={{ pointerEvents: 'none' }}>
      <canvas aria-hidden="true" ref={ref} width={w} height={h} style={{ width: '100%', height: '100%', display: 'block' }} />
    </foreignObject>
  )
}

export const coverageOverlay: OverlayPlugin = {
  id: 'coverage',
  label: 'Coverage heatmap',
  description: 'Shades every intersection by the drive time to the nearest vehicle (green = close, red = far).',
  icon: Radar,
  defaultOn: false,
  under: true,
  render: { map2d: (ctx) => <CoverageLayer {...ctx} /> },
}
