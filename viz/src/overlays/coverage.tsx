import { useEffect, useRef } from 'react'
import { Radar } from 'lucide-react'
import { nearestResponseTime } from '@/engine/sample'
import { distanceColor } from '@/views/colors'
import type { Map2DContext, OverlayPlugin } from './types'

/** Heatmap of response minutes, including locked travel and service. */
function CoverageLayer({ frame, sy }: Map2DContext) {
  const ref = useRef<HTMLCanvasElement>(null)
  const { minX, maxX, minY, maxY } = frame.bounds
  const w = maxX - minX + 1
  const h = maxY - minY + 1
  useEffect(() => {
    const ctx = ref.current?.getContext('2d')
    if (!ctx) return
    const img = ctx.createImageData(w, h)
    const scale = Math.max(8, (w + h) / 2)
    for (let j = 0; j < h; j++) {
      for (let i = 0; i < w; i++) {
        const d = nearestResponseTime(minX + i, maxY - j, frame.vehicles)
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
  description: 'Response time including remaining locked work and Manhattan travel (green = soon, red = later).',
  icon: Radar,
  defaultOn: false,
  under: true,
  render: { map2d: (ctx) => <CoverageLayer {...ctx} /> },
}
