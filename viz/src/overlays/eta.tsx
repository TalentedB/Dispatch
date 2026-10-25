import { Timer } from 'lucide-react'
import { CALL_STATUS } from '@/engine/status'
import type { OverlayPlugin } from './types'

export const etaOverlay: OverlayPlugin = {
  id: 'eta',
  label: 'Time to complete',
  description: 'Wait and response bars on the timeline. On the top-down map, hover a vehicle or call for times.',
  icon: Timer,
  defaultOn: true,
  render: {
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
