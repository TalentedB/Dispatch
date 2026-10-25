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

/** Deterministic per-block noise, so buildings and parks stay put between renders. */
const hash = (x: number, y: number) => {
  const h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453
  return h - Math.floor(h)
}

type Range = { x0: number; x1: number; y0: number; y1: number }
/** Flat list of rectangles in world units (y already flipped): x0, y0, x1, y1, x0, ... */
type Rects = number[]

const street = (n: number) => (n === 0 ? 0.2 : n % 5 === 0 ? 0.15 : 0.08)
const BUILDING_TONES = 3

/**
 * Vehicles drive along grid lines, so the lines are streets and each unit cell is
 * a city block. Every 5th street is a wider avenue; the axes through base are the
 * main avenues. Blocks are split into a few buildings (deterministic per block) and
 * some are parks with trees. `detail` off gives plain lots, for when blocks are tiny.
 */
function cityGeometry({ x0, x1, y0, y1 }: Range, detail: boolean) {
  const lots: Rects = []
  const parks: Rects = []
  const trees: Rects = []
  const buildings: Rects[] = Array.from({ length: BUILDING_TONES }, () => [])
  for (let x = x0; x < x1; x++) {
    for (let y = y0; y < y1; y++) {
      const ax = x + street(x)
      const bx = x + 1 - street(x + 1)
      const ay = sy(y + 1) + street(y + 1)
      const by = sy(y) - street(y)
      if (hash(x, y) < 0.07) {
        parks.push(ax, ay, bx, by)
        if (detail) {
          for (let i = 0; i < 4; i++) {
            const tx = ax + 0.15 + (bx - ax - 0.3) * hash(x + i * 13, y)
            const ty = ay + 0.15 + (by - ay - 0.3) * hash(x, y + i * 17)
            trees.push(tx - 0.07, ty - 0.07, tx + 0.07, ty + 0.07)
          }
        }
        continue
      }
      lots.push(ax, ay, bx, by)
      if (!detail) continue
      // Split the lot into 1, 2 or 4 buildings with small gaps between them.
      const g = 0.05
      const [ix0, iy0, ix1, iy1] = [ax + g, ay + g, bx - g, by - g]
      const mx = ix0 + (ix1 - ix0) * (0.4 + 0.2 * hash(y, x))
      const my = iy0 + (iy1 - iy0) * (0.4 + 0.2 * hash(x * 3, y * 7))
      const pattern = Math.floor(hash(x * 7, y * 3) * 4)
      const parts =
        pattern === 0 ? [ix0, iy0, ix1, iy1]
          : pattern === 1 ? [ix0, iy0, mx - g / 2, iy1, mx + g / 2, iy0, ix1, iy1]
            : pattern === 2 ? [ix0, iy0, ix1, my - g / 2, ix0, my + g / 2, ix1, iy1]
              : [ix0, iy0, mx - g / 2, my - g / 2, mx + g / 2, iy0, ix1, my - g / 2,
                ix0, my + g / 2, mx - g / 2, iy1, mx + g / 2, my + g / 2, ix1, iy1]
      for (let i = 0; i < parts.length; i += 4) {
        buildings[Math.floor(hash(x * 5 + i, y * 11 - i) * BUILDING_TONES)].push(parts[i], parts[i + 1], parts[i + 2], parts[i + 3])
      }
    }
  }
  return { lots, parks, trees, buildings }
}

/** The part of the grid on screen, snapped outward to 8-block chunks so panning rarely rebuilds geometry. */
function visibleRange(vb: number[], bounds: Bounds): Range {
  const snap = 8
  const pad = 40 // never draw more than this far past the service area
  const lo = (v: number) => Math.floor(v / snap) * snap
  const hi = (v: number) => Math.ceil(v / snap) * snap
  return {
    x0: Math.max(lo(vb[0]) - 1, bounds.minX - pad),
    x1: Math.min(hi(vb[0] + vb[2]) + 1, bounds.maxX + pad),
    y0: Math.max(lo(-(vb[1] + vb[3])) - 1, bounds.minY - pad),
    y1: Math.min(hi(-vb[1]) + 1, bounds.maxY + pad),
  }
}

/**
 * The city is drawn to a canvas, not SVG: it is thousands of shapes that only change
 * on pan or zoom, while the SVG on top re-renders every animation frame.
 */
function CityCanvas({ bounds, vb, width, height }: { bounds: Bounds; vb: number[]; width: number; height: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const scale = width / vb[2]
  const r = visibleRange(vb, bounds)
  const detail = scale >= 12 // a block is at least 12 screen pixels
  const geo = useMemo(() => cityGeometry({ x0: r.x0, x1: r.x1, y0: r.y0, y1: r.y1 }, detail), [r.x0, r.x1, r.y0, r.y1, detail])
  const [vx, vy] = vb

  useEffect(() => {
    const canvas = ref.current
    const g = canvas?.getContext('2d')
    if (!canvas || !g) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.round(width * dpr)
    canvas.height = Math.round(height * dpr)
    g.setTransform(dpr * scale, 0, 0, dpr * scale, -vx * scale * dpr, -vy * scale * dpr)
    const px = 1 / scale
    const rects = (list: Rects, radius: number) => {
      g.beginPath()
      for (let i = 0; i < list.length; i += 4) g.roundRect(list[i], list[i + 1], list[i + 2] - list[i], list[i + 3] - list[i + 1], radius)
    }
    g.fillStyle = themeColor('map-road')
    g.fillRect(vx, vy, width * px, height * px)
    rects(geo.lots, 0.05)
    g.fillStyle = themeColor('map-lot')
    g.fill()
    g.strokeStyle = themeColor('map-building-edge')
    g.lineWidth = 0.75 * px
    geo.buildings.forEach((list, i) => {
      rects(list, 0.03)
      g.fillStyle = themeColor(`map-building-${i + 1}`)
      g.fill()
      g.stroke()
    })
    rects(geo.parks, 0.06)
    g.fillStyle = themeColor('map-park')
    g.fill()
    rects(geo.trees, 0.07)
    g.fillStyle = themeColor('map-tree')
    g.fill()

    // Avenue centre lines; the two through base are dashed.
    g.strokeStyle = themeColor('map-lane')
    g.lineWidth = px
    g.beginPath()
    for (let x = Math.ceil(r.x0 / 5) * 5; x <= r.x1; x += 5) if (x !== 0) { g.moveTo(x, sy(r.y0)); g.lineTo(x, sy(r.y1)) }
    for (let y = Math.ceil(r.y0 / 5) * 5; y <= r.y1; y += 5) if (y !== 0) { g.moveTo(r.x0, sy(y)); g.lineTo(r.x1, sy(y)) }
    g.stroke()
    g.lineWidth = 1.5 * px
    g.setLineDash([7 * px, 6 * px])
    g.beginPath()
    g.moveTo(r.x0, 0); g.lineTo(r.x1, 0)
    g.moveTo(0, sy(r.y0)); g.lineTo(0, sy(r.y1))
    g.stroke()

    // Everything outside the service area is the same city, washed out.
    const { minX, maxX, minY, maxY } = bounds
    g.beginPath()
    g.rect(vx, vy, width * px, height * px)
    g.rect(minX, sy(maxY), maxX - minX, maxY - minY)
    g.globalAlpha = 0.55
    g.fillStyle = themeColor('map-road')
    g.fill('evenodd')
    g.globalAlpha = 0.5
    g.strokeStyle = themeColor('map-axis')
    g.lineWidth = px
    g.setLineDash([3 * px, 4 * px])
    g.strokeRect(minX, sy(maxY), maxX - minX, maxY - minY)
    g.globalAlpha = 1
    g.setLineDash([])
  }, [geo, bounds, vx, vy, scale, width, height, r.x0, r.x1, r.y0, r.y1])

  return <canvas ref={ref} aria-hidden="true" className="pointer-events-none absolute inset-0" style={{ width, height }} />
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

  // Screen space covered by floating controls (demo mode) or the guidance line, kept clear when fitting.
  const demo = ref.current?.closest('.is-demo') != null
  const inset = demo ? { top: 84, bottom: 200 } : { top: 16, bottom: 40 }
  const fit = Math.min(width / (maxX - minX + 2), (height - inset.top - inset.bottom) / (maxY - minY + 2)) || 1
  const scale = fit * view.zoom
  const px = 1 / scale
  const shift = (inset.bottom - inset.top) / 2 / scale
  const vb = [view.cx - width / 2 / scale, view.cy - height / 2 / scale + shift, width / scale, height / scale]

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
      {width > 0 && <CityCanvas bounds={prepared.bounds} vb={vb} width={width} height={height} />}
      {width > 0 && (
        <svg role="img" aria-label="City grid showing emergency calls, base, and vehicle positions" width={width} height={height} viewBox={vb.join(' ')} className="relative block select-none">
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
