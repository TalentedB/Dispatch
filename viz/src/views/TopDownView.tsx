import { themeColor } from '@/lib/theme'
import { useEffect, useMemo, useRef, useState, type PointerEvent, type WheelEvent } from 'react'
import { Ambulance, Check, HeartPulse, Hospital, Map as MapIcon, Siren } from 'lucide-react'
import { OVERLAYS } from '@/overlays/registry'
import type { Map2DContext } from '@/overlays/types'
import { CALL_STATUS, vehicleColor } from '@/engine/status'
import type { Bounds, CallFrame, VehicleFrame } from '@/engine/sample'
import { useSize } from './useSize'
import type { ViewPlugin, ViewProps } from './types'

const sy = (y: number) => -y

/** Deterministic per-block noise, so parks stay put between renders. */
const hash = (x: number, y: number) => {
  const h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453
  return h - Math.floor(h)
}

/** One rounded rectangle as path commands (world units). */
function roundRect(x0: number, y0: number, x1: number, y1: number, r: number) {
  return `M${x0 + r} ${y0}H${x1 - r}A${r} ${r} 0 0 1 ${x1} ${y0 + r}V${y1 - r}A${r} ${r} 0 0 1 ${x1 - r} ${y1}` +
    `H${x0 + r}A${r} ${r} 0 0 1 ${x0} ${y1 - r}V${y0 + r}A${r} ${r} 0 0 1 ${x0 + r} ${y0}Z`
}

/**
 * Vehicles drive along grid lines, so the lines are streets and each unit cell is
 * a city block. Every 5th street is a wider avenue; the axes through base are the
 * main avenues. A few blocks are parks. Built as two paths so 80x80 maps stay cheap.
 */
function cityPaths({ minX, maxX, minY, maxY }: Bounds) {
  const street = (n: number) => (n === 0 ? 0.22 : n % 5 === 0 ? 0.16 : 0.09)
  let blocks = ''
  let parks = ''
  for (let x = minX; x < maxX; x++) {
    for (let y = minY; y < maxY; y++) {
      const d = roundRect(x + street(x), sy(y + 1) + street(y + 1), x + 1 - street(x + 1), sy(y) - street(y), 0.07)
      if (hash(x, y) < 0.06) parks += d
      else blocks += d
    }
  }
  return { blocks, parks }
}

function City({ bounds, px }: { bounds: Bounds; px: number }) {
  const { blocks, parks } = useMemo(() => cityPaths(bounds), [bounds])
  const { minX, maxX, minY, maxY } = bounds
  return (
    <g>
      <rect x={minX} y={sy(maxY)} width={maxX - minX} height={maxY - minY} fill={themeColor('map-paper')} />
      <path d={blocks} fill={themeColor('map-block')} stroke={themeColor('map-block-edge')} strokeWidth={px} />
      <path d={parks} fill={themeColor('map-park')} stroke={themeColor('map-park-edge')} strokeWidth={px} />
      <line x1={minX} x2={maxX} y1={0} y2={0} stroke={themeColor('map-major')} strokeWidth={1.5 * px} strokeDasharray={`${6 * px} ${5 * px}`} />
      <line x1={0} x2={0} y1={sy(minY)} y2={sy(maxY)} stroke={themeColor('map-major')} strokeWidth={1.5 * px} strokeDasharray={`${6 * px} ${5 * px}`} />
    </g>
  )
}

/** A small numbered tag pinned to the top-right of a marker. */
function Tag({ x, y, text, color, px }: { x: number; y: number; text: string; color: string; px: number }) {
  const w = (text.length * 5.6 + 7) * px
  const h = 12 * px
  return (
    <g style={{ pointerEvents: 'none' }}>
      <rect x={x - h / 2} y={y - h / 2} width={w} height={h} rx={h / 2} fill={themeColor('map-paper')} stroke={color} strokeWidth={px} />
      <text x={x - h / 2 + w / 2} y={y} textAnchor="middle" dominantBaseline="central" fontSize={8.5 * px} fontWeight={700} fill={color}
        style={{ fontVariantNumeric: 'tabular-nums' }}>
        {text}
      </text>
    </g>
  )
}

function BaseMarker({ px }: { px: number }) {
  const s = 24 * px
  return (
    <g>
      <rect x={-s / 2 - 3 * px} y={-s / 2 - 3 * px} width={s + 6 * px} height={s + 6 * px} rx={8 * px}
        fill={themeColor('map-paper')} opacity={0.85} />
      <rect x={-s / 2} y={-s / 2} width={s} height={s} rx={6 * px} fill={themeColor('map-base')} />
      <Hospital x={-8 * px} y={-8 * px} size={16 * px} color={themeColor('map-mark')} strokeWidth={2} />
    </g>
  )
}

function CallMarker({ c, px }: { c: CallFrame; px: number }) {
  const color = CALL_STATUS[c.status].color
  const x = c.call.x
  const y = sy(c.call.y)
  if (c.status === 'done') {
    return (
      <g opacity={0.55}>
        <circle cx={x} cy={y} r={5.5 * px} fill={color} />
        <Check x={x - 3.5 * px} y={y - 3.5 * px} size={7 * px} color={themeColor('map-paper')} strokeWidth={3} />
      </g>
    )
  }
  const r = 11 * px
  const Icon = c.status === 'on_scene' ? HeartPulse : Siren
  // On-scene progress as a ring that fills clockwise from 12 o'clock.
  const ring = 2 * Math.PI * (r + 3 * px)
  return (
    <g>
      {c.status === 'waiting' && (
        <circle cx={x} cy={y} r={r} fill="none" stroke={color} strokeWidth={2 * px}>
          <animate attributeName="r" values={`${r};${r * 2.1}`} dur="1.6s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.7;0" dur="1.6s" repeatCount="indefinite" />
        </circle>
      )}
      {c.status === 'on_scene' && (
        <>
          <circle cx={x} cy={y} r={r + 3 * px} fill="none" stroke={color} strokeOpacity={0.2} strokeWidth={2.5 * px} />
          <circle cx={x} cy={y} r={r + 3 * px} fill="none" stroke={color} strokeWidth={2.5 * px} strokeLinecap="round"
            strokeDasharray={`${ring * c.progress} ${ring}`} transform={`rotate(-90 ${x} ${y})`} />
        </>
      )}
      <circle cx={x} cy={y} r={r} fill={color} stroke={themeColor('map-paper')} strokeWidth={1.5 * px} />
      <Icon x={x - 7 * px} y={y - 7 * px} size={14 * px} color={themeColor('map-paper')} strokeWidth={2.25} />
      <Tag x={x + 11 * px} y={y - 10 * px} text={`#${c.call.id}`} color={color} px={px} />
    </g>
  )
}

function VehicleMarker({ v, px }: { v: VehicleFrame; px: number }) {
  const color = vehicleColor(v.id)
  const x = v.x
  const y = sy(v.y)
  const s = 22 * px
  // The icon faces east; mirror it while the vehicle heads west.
  const next = v.remainingPath[1]
  const west = next !== undefined && next[0] < v.x
  return (
    <g>
      <rect x={x - s / 2} y={y - s / 2} width={s} height={s} rx={6 * px} fill={color}
        stroke={themeColor('map-paper')} strokeWidth={2 * px} />
      <g transform={west ? `translate(${2 * x} 0) scale(-1 1)` : undefined}>
        <Ambulance x={x - 7.5 * px} y={y - 7.5 * px} size={15 * px} color={themeColor('map-paper')} strokeWidth={2.25} />
      </g>
      <Tag x={x + 11 * px} y={y - 11 * px} text={`${v.id}`} color={color} px={px} />
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
          <City bounds={prepared.bounds} px={px} />
          {active.filter((o) => o.under).map((o) => <g key={o.id}>{o.render.map2d!(ctx)}</g>)}
          <BaseMarker px={px} />
          {/* Done calls first so live ones draw on top. */}
          {frame.calls.filter((c) => c.status === 'done').map((c) => <CallMarker key={c.call.id} c={c} px={px} />)}
          {frame.calls.filter((c) => c.status !== 'future' && c.status !== 'done').map((c) => <CallMarker key={c.call.id} c={c} px={px} />)}
          {frame.vehicles.map((v) => <VehicleMarker key={v.id} v={v} px={px} />)}
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
