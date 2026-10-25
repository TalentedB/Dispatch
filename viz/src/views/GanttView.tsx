import { useRef, type PointerEvent } from 'react'
import { GanttChart } from 'lucide-react'
import { OVERLAYS } from '@/overlays/registry'
import type { GanttContext } from '@/overlays/types'
import { CALL_STATUS, VEHICLE_STATUS, vehicleColor } from '@/engine/status'
import { clockActions, formatClock } from '@/playback/clock'
import { useSize } from './useSize'
import type { ViewPlugin, ViewProps } from './types'

const GUTTER = 64
const TOP = 26
const WAIT_LANE = 44

function tickStep(minutes: number, width: number) {
  const target = minutes / Math.max(2, width / 90)
  return [5, 10, 15, 30, 60, 120, 240, 480].find((s) => s >= target) ?? 720
}

function Gantt({ prepared, frame, overlays }: ViewProps) {
  const ref = useRef<HTMLDivElement>(null)
  const { width, height } = useSize(ref)
  const { start, end } = prepared.trace.span
  const vehicles = prepared.trace.vehicles
  const plotW = Math.max(1, width - GUTTER - 12)
  const tx = (t: number) => GUTTER + ((t - start) / (end - start)) * plotW
  const avail = height - TOP - WAIT_LANE - 16
  const laneH = Math.max(8, Math.min(30, avail / vehicles.length - 6))
  const laneY = (id: number) => TOP + 8 + id * (laneH + 6)
  const ctx: GanttContext = { prepared, frame, tx, laneY, laneH }
  const step = tickStep(end - start, plotW)
  const ticks = []
  for (let t = Math.ceil(start / step) * step; t <= end; t += step) ticks.push(t)

  const waitTop = laneY(vehicles.length) + 4
  const maxWait = Math.max(1, ...prepared.waitingSeries)
  const area = prepared.waitingSeries
    .map((w, i) => `${tx(start + i)},${waitTop + WAIT_LANE - (w / maxWait) * (WAIT_LANE - 8)}`)
    .join(' ')

  const seek = (e: PointerEvent) => {
    if (e.buttons !== 1) return
    const rect = ref.current!.getBoundingClientRect()
    clockActions.seek(start + ((e.clientX - rect.left - GUTTER) / plotW) * (end - start))
  }

  return (
    <div ref={ref} className="absolute inset-0 cursor-crosshair overflow-hidden" onPointerDown={seek} onPointerMove={seek}>
      {width > 0 && (
        <svg width={width} height={height} className="block select-none">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={tx(t)} x2={tx(t)} y1={TOP - 4} y2={height} stroke="#27272a" />
              <text x={tx(t)} y={14} textAnchor="middle" fontSize={10} fill="#71717a">{formatClock(t)}</text>
            </g>
          ))}
          {vehicles.map((v) => (
            <g key={v.id}>
              <rect x={GUTTER} y={laneY(v.id)} width={plotW} height={laneH} rx={4} fill="#18181b" />
              <circle cx={14} cy={laneY(v.id) + laneH / 2} r={5} fill={vehicleColor(v.id)} />
              <text x={24} y={laneY(v.id) + laneH / 2} dominantBaseline="central" fontSize={11} fill="#a1a1aa" fontWeight={600}>V{v.id}</text>
              {v.segments.map((s, i) => (
                <rect key={i} x={tx(s.start)} y={laneY(v.id) + (s.kind === 'on_job' ? 0 : laneH * 0.2)}
                  width={Math.max(0.5, tx(s.end) - tx(s.start))} height={s.kind === 'on_job' ? laneH : laneH * 0.6}
                  rx={3} fill={VEHICLE_STATUS[s.kind].color} opacity={s.interrupted ? 0.45 : 0.9}>
                  <title>{`V${v.id} ${VEHICLE_STATUS[s.kind].label}${s.callId !== undefined ? ` #${s.callId}` : ''}: ${formatClock(s.start)}–${formatClock(s.end)}`}</title>
                </rect>
              ))}
            </g>
          ))}
          <text x={8} y={waitTop + WAIT_LANE / 2} dominantBaseline="central" fontSize={10} fill="#71717a">waiting</text>
          <polyline points={`${tx(start)},${waitTop + WAIT_LANE} ${area} ${tx(end)},${waitTop + WAIT_LANE}`}
            fill={CALL_STATUS.waiting.color} fillOpacity={0.25} stroke={CALL_STATUS.waiting.color} strokeWidth={1} />
          {OVERLAYS.filter((o) => overlays.has(o.id) && o.render.gantt).map((o) => <g key={o.id}>{o.render.gantt!(ctx)}</g>)}
          <line x1={tx(frame.t)} x2={tx(frame.t)} y1={TOP - 6} y2={height} stroke="#fafafa" strokeWidth={1.5} />
          <rect x={tx(frame.t) - 26} y={2} width={52} height={16} rx={8} fill="#fafafa" />
          <text x={tx(frame.t)} y={10} textAnchor="middle" dominantBaseline="central" fontSize={10} fontWeight={700} fill="#09090b">
            {formatClock(frame.t)}
          </text>
        </svg>
      )}
    </div>
  )
}

export const ganttView: ViewPlugin = {
  id: 'gantt',
  label: 'Timeline',
  icon: GanttChart,
  slot: 'gantt',
  component: Gantt,
}
