import { themeColor } from '@/lib/theme'
import { useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from 'react'
import { Map as MapIcon } from 'lucide-react'
import { OVERLAYS } from '@/overlays/registry'
import type { Map2DContext } from '@/overlays/types'
import { CALL_STATUS, vehicleColor } from '@/engine/status'
import type { CallFrame } from '@/engine/sample'
import { useSize } from './useSize'
import type { ViewPlugin, ViewProps } from './types'

const sy = (y: number) => -y

function GridLines({ minX, maxX, minY, maxY, px }: { minX: number; maxX: number; minY: number; maxY: number; px: number }) {
  const lines = []
  for (let x = minX; x <= maxX; x++) {
    const major = x % 5 === 0
    lines.push(<line key={`x${x}`} x1={x} x2={x} y1={sy(minY)} y2={sy(maxY)}
      stroke={x === 0 ? themeColor('map-axis') : major ? themeColor('map-major') : themeColor('map-grid')} strokeWidth={(x === 0 ? 2 : 1) * px} />)
  }
  for (let y = minY; y <= maxY; y++) {
    const major = y % 5 === 0
    lines.push(<line key={`y${y}`} y1={sy(y)} y2={sy(y)} x1={minX} x2={maxX}
      stroke={y === 0 ? themeColor('map-axis') : major ? themeColor('map-major') : themeColor('map-grid')} strokeWidth={(y === 0 ? 2 : 1) * px} />)
  }
  return <g>{lines}</g>
}

function CallMarker({ c, px }: { c: CallFrame; px: number }) {
  const color = CALL_STATUS[c.status].color
  const x = c.call.x
  const y = sy(c.call.y)
  const r = 7 * px
  if (c.status === 'done') {
    return <circle cx={x} cy={y} r={3.5 * px} fill={color} opacity={0.45} />
  }
  return (
    <g>
      <rect x={x - r} y={y - r} width={2 * r} height={2 * r} rx={2 * px} fill={color}
        transform={`rotate(45 ${x} ${y})`} stroke={themeColor('map-paper')} strokeWidth={1.5 * px} />
      <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={8 * px} fontWeight={800} fill={themeColor('map-paper')}>
        {c.call.id}
      </text>
    </g>
  )
}

function TopDown({ prepared, frame, overlays }: ViewProps) {
  const ref = useRef<HTMLDivElement>(null)
  const { width, height } = useSize(ref)
  const { minX, maxX, minY, maxY } = prepared.bounds
  const [view, setView] = useState({ zoom: 1, cx: (minX + maxX) / 2, cy: sy((minY + maxY) / 2) })
  const drag = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null)

  useEffect(() => {
    setView({ zoom: 1, cx: (minX + maxX) / 2, cy: sy((minY + maxY) / 2) })
  }, [minX, maxX, minY, maxY])

  const fit = Math.min(width / (maxX - minX + 2), height / (maxY - minY + 2)) || 1
  const scale = fit * view.zoom
  const px = 1 / scale
  const vb = [view.cx - width / 2 / scale, view.cy - height / 2 / scale, width / scale, height / scale]

  const onWheel = (e: WheelEvent) => {
    const rect = ref.current!.getBoundingClientRect()
    const wx = vb[0] + (e.clientX - rect.left) / scale
    const wy = vb[1] + (e.clientY - rect.top) / scale
    const zoom = Math.min(40, Math.max(0.3, view.zoom * Math.exp(-e.deltaY * 0.0015)))
    const k = view.zoom / zoom
    setView({ zoom, cx: wx + (view.cx - wx) * k, cy: wy + (view.cy - wy) * k })
  }
  const onDown = (e: PointerEvent) => {
    ;(e.target as Element).setPointerCapture(e.pointerId)
    drag.current = { x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy }
  }
  const onMove = (e: PointerEvent) => {
    const d = drag.current
    if (d) setView((v) => ({ ...v, cx: d.cx - (e.clientX - d.x) / scale, cy: d.cy - (e.clientY - d.y) / scale }))
  }

  const ctx: Map2DContext = { prepared, frame, sy, px }
  const active = useMemo(() => OVERLAYS.filter((o) => overlays.has(o.id) && o.render.map2d), [overlays])

  return (
    <div ref={ref} className="absolute inset-0 cursor-grab touch-none active:cursor-grabbing"
      onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={() => (drag.current = null)}
      onDoubleClick={() => setView({ zoom: 1, cx: (minX + maxX) / 2, cy: sy((minY + maxY) / 2) })}>
      {width > 0 && (
        <svg role="img" aria-label="City grid showing emergency calls, base, and vehicle positions" width={width} height={height} viewBox={vb.join(' ')} className="block select-none">
          <GridLines minX={minX} maxX={maxX} minY={minY} maxY={maxY} px={px} />
          {active.filter((o) => o.under).map((o) => <g key={o.id}>{o.render.map2d!(ctx)}</g>)}
          <rect x={-9 * px} y={-9 * px} width={18 * px} height={18 * px} rx={4 * px} fill={themeColor('map-base')} stroke={themeColor('map-mark')} strokeWidth={1.5 * px} />
          <path d={`M 0 ${-5 * px} V ${5 * px} M ${-5 * px} 0 H ${5 * px}`} stroke={themeColor('map-mark')} strokeWidth={2.5 * px} strokeLinecap="round" />
          {frame.calls.filter((c) => c.status !== 'future').map((c) => <CallMarker key={c.call.id} c={c} px={px} />)}
          {frame.vehicles.map((v) => (
            <g key={v.id}>
              <circle cx={v.x} cy={sy(v.y)} r={9 * px} fill={vehicleColor(v.id)} stroke={themeColor('map-paper')} strokeWidth={2 * px} />
              <text x={v.x} y={sy(v.y)} textAnchor="middle" dominantBaseline="central" fontSize={9 * px} fontWeight={800} fill={themeColor('map-paper')}>
                {v.id}
              </text>
            </g>
          ))}
          {active.filter((o) => !o.under).map((o) => <g key={o.id}>{o.render.map2d!(ctx)}</g>)}
        </svg>
      )}
      <div className="map-guidance">
        <span><kbd>Scroll</kbd> Zoom <kbd>Drag</kbd> Pan <kbd>Double-click</kbd> Reset</span>
        <span>1 block = 1 minute <strong>North ↑</strong></span>
      </div>
    </div>
  )
}

export const topDownView: ViewPlugin = {
  id: 'topdown',
  label: 'Top-down',
  icon: MapIcon,
  slot: 'map2d',
  component: TopDown,
}
