import { Route } from 'lucide-react'
import { pathLength, pointAlong, type VehicleFrame } from '@/engine/sample'
import { VEHICLE_STATUS } from '@/engine/status'
import { Label3D, Line3D, Pill, toPoints, world } from './shared'
import type { OverlayPlugin } from './types'

const assigned = (v: VehicleFrame) =>
  (v.status === 'to_job' || v.status === 'reposition') && v.blocksToTarget > 0

const label = (v: VehicleFrame) =>
  `${Math.ceil(v.blocksToTarget)} blk${v.call ? ` → #${v.call.id}` : ''}`

export const assignmentOverlay: OverlayPlugin = {
  id: 'assignment',
  label: 'Distance to assignment',
  description: 'Route each responding vehicle still has to drive, with the remaining blocks.',
  icon: Route,
  defaultOn: true,
  render: {
    map2d: ({ frame, sy, px }) =>
      frame.vehicles.filter(assigned).map((v) => {
        const color = VEHICLE_STATUS[v.status].color
        const mid = pointAlong(v.remainingPath, pathLength(v.remainingPath) / 2).p
        return (
          <g key={v.id}>
            <polyline points={toPoints(v.remainingPath, sy)} fill="none" stroke={color} strokeWidth={2.5 * px}
              strokeDasharray={`${7 * px} ${5 * px}`} strokeLinecap="round" strokeLinejoin="round"
              className="animate-[dash_1s_linear_infinite]" style={{ ['--dash' as string]: `${-12 * px}` }} />
            <Pill x={mid[0]} y={sy(mid[1])} text={label(v)} color={color} px={px} />
          </g>
        )
      }),
    map3d: ({ frame, heightAt }) =>
      frame.vehicles.filter(assigned).map((v) => {
        const color = VEHICLE_STATUS[v.status].color
        const mid = pointAlong(v.remainingPath, pathLength(v.remainingPath) / 2).p
        return (
          <group key={v.id}>
            <Line3D path={v.remainingPath} height={heightAt} color={color} width={2.5} dashed />
            <Label3D at={world(mid[0], mid[1], heightAt(mid[0], mid[1]))} text={label(v)} color={color} dy={0} />
          </group>
        )
      }),
  },
}
