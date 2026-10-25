import { themeColor } from '@/lib/theme'
import { Activity } from 'lucide-react'
import type { OverlayPlugin } from './types'

export const statusOverlay: OverlayPlugin = {
  id: 'status',
  label: 'Assignment state',
  description: 'Call numbers on the timeline. On the maps, a vehicle\'s colour shows its state.',
  icon: Activity,
  defaultOn: true,
  render: {
    gantt: ({ prepared, tx, laneY, laneH }) =>
      prepared.trace.vehicles.flatMap((v) =>
        v.segments
          .filter((s) => s.callId !== undefined && s.kind === 'on_job' && tx(s.end) - tx(s.start) > 18)
          .map((s, i) => (
            <text key={`${v.id}-${i}`} x={(tx(s.start) + tx(s.end)) / 2} y={laneY(v.id) + laneH / 2}
              textAnchor="middle" dominantBaseline="central" fontSize={10} fontWeight={700} fill={themeColor('map-paper')}
              style={{ pointerEvents: 'none' }}>
              #{s.callId}
            </text>
          )),
      ),
  },
}
