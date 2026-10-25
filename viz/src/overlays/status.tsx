import { Activity } from 'lucide-react'
import { VEHICLE_STATUS } from '@/engine/status'
import { Label3D, Pill, world } from './shared'
import type { OverlayPlugin } from './types'

export const statusOverlay: OverlayPlugin = {
  id: 'status',
  label: 'Assignment state',
  description: 'Idle, responding, on scene, returning, repositioning: a halo and badge on every vehicle.',
  icon: Activity,
  defaultOn: true,
  render: {
    map2d: ({ frame, sy, px }) =>
      frame.vehicles.map((v) => {
        const s = VEHICLE_STATUS[v.status]
        return (
          <g key={v.id}>
            <circle cx={v.x} cy={sy(v.y)} r={14 * px} fill="none" stroke={s.color} strokeWidth={2 * px} opacity={0.9}
              strokeDasharray={v.status === 'idle' ? `${3 * px} ${3 * px}` : undefined} />
            <Pill x={v.x} y={sy(v.y)} dy={24} px={px} text={`V${v.id} ${s.short}`} color={s.color} solid />
          </g>
        )
      }),
    map3d: ({ frame, heightAt }) =>
      frame.vehicles.map((v) => {
        const s = VEHICLE_STATUS[v.status]
        const at = world(v.x, v.y, heightAt(v.x, v.y))
        return (
          <group key={v.id}>
            <mesh position={[at[0], at[1] + 0.05, at[2]]} rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[0.75, 0.95, 32]} />
              <meshBasicMaterial color={s.color} transparent opacity={0.9} />
            </mesh>
            <Label3D at={at} text={`V${v.id} ${s.short}`} color={s.color} dy={24} />
          </group>
        )
      }),
    gantt: ({ prepared, tx, laneY, laneH }) =>
      prepared.trace.vehicles.flatMap((v) =>
        v.segments
          .filter((s) => s.callId !== undefined && s.kind === 'on_job' && tx(s.end) - tx(s.start) > 18)
          .map((s, i) => (
            <text key={`${v.id}-${i}`} x={(tx(s.start) + tx(s.end)) / 2} y={laneY(v.id) + laneH / 2}
              textAnchor="middle" dominantBaseline="central" fontSize={10} fontWeight={700} fill="#09090b"
              style={{ pointerEvents: 'none' }}>
              #{s.callId}
            </text>
          )),
      ),
  },
}
