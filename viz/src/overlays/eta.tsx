import { Timer } from 'lucide-react'
import { formatMinutes } from '@/playback/clock'
import { CALL_STATUS, VEHICLE_STATUS } from '@/engine/status'
import type { VehicleFrame } from '@/engine/sample'
import { Label3D, Pill, world } from './shared'
import type { OverlayPlugin } from './types'

function etaText(v: VehicleFrame): string | null {
  if (v.status === 'to_job' && v.minutesToArrive !== undefined && v.minutesToComplete !== undefined)
    return `ETA ${formatMinutes(v.minutesToArrive)} · done ${formatMinutes(v.minutesToComplete)}`
  if (v.status === 'on_job' && v.minutesToComplete !== undefined) return `done in ${formatMinutes(v.minutesToComplete)}`
  if ((v.status === 'to_base' || v.status === 'reposition') && v.minutesToArrive) return `home in ${formatMinutes(v.minutesToArrive)}`
  return null
}

function arc(cx: number, cy: number, r: number, f: number) {
  const a = Math.min(f, 0.9999) * Math.PI * 2
  const x = cx + r * Math.sin(a)
  const y = cy - r * Math.cos(a)
  return `M ${cx} ${cy - r} A ${r} ${r} 0 ${a > Math.PI ? 1 : 0} 1 ${x} ${y}`
}

export const etaOverlay: OverlayPlugin = {
  id: 'eta',
  label: 'Time to complete',
  description: 'ETA to the scene and minutes until the job is done; progress rings on active scenes; wait times.',
  icon: Timer,
  defaultOn: true,
  render: {
    map2d: ({ frame, sy, px }) => (
      <>
        {frame.calls.filter((c) => c.status === 'on_scene').map((c) => (
          <path key={`r${c.call.id}`} d={arc(c.call.x, sy(c.call.y), 13 * px, c.progress)} fill="none"
            stroke={CALL_STATUS.done.color} strokeWidth={3 * px} strokeLinecap="round" />
        ))}
        {frame.calls.filter((c) => c.status === 'waiting').map((c) => (
          <Pill key={`w${c.call.id}`} x={c.call.x} y={sy(c.call.y)} dy={22} px={px}
            text={`wait ${formatMinutes(c.waited, true)}`} color={CALL_STATUS.waiting.color} />
        ))}
        {frame.vehicles.map((v) => {
          const text = etaText(v)
          return text && <Pill key={v.id} x={v.x} y={sy(v.y)} dy={-22} px={px} text={text} color={VEHICLE_STATUS[v.status].color} />
        })}
      </>
    ),
    map3d: ({ frame, heightAt }) =>
      frame.vehicles.map((v) => {
        const text = etaText(v)
        return text && <Label3D key={v.id} at={world(v.x, v.y, heightAt(v.x, v.y))} text={text} color={VEHICLE_STATUS[v.status].color} dy={44} />
      }),
    gantt: ({ prepared, tx, laneY }) =>
      prepared.calls.map((c) => {
        if (c.vehicle === undefined || c.arrive === undefined) return null
        const y = laneY(c.vehicle) - 5
        const wait = c.dispatch ?? c.arrive
        return (
          <g key={c.call.id}>
            <title>{`Call #${c.call.id}: waited ${wait - c.call.time} min, response ${c.arrive - c.call.time} min`}</title>
            {wait > c.call.time && <rect x={tx(c.call.time)} y={y} width={tx(wait) - tx(c.call.time)} height={3} fill={CALL_STATUS.waiting.color} rx={1.5} />}
            <rect x={tx(wait)} y={y} width={Math.max(1, tx(c.arrive) - tx(wait))} height={3} fill={CALL_STATUS.dispatched.color} opacity={0.6} rx={1.5} />
            <circle cx={tx(c.call.time)} cy={y + 1.5} r={2.5} fill={CALL_STATUS.waiting.color} />
          </g>
        )
      }),
  },
}
