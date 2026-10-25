import { Route } from 'lucide-react'
import type { VehicleFrame } from '@/engine/sample'
import { VEHICLE_STATUS } from '@/engine/status'
import { Line3D, toPoints } from './shared'
import type { OverlayPlugin } from './types'

const assigned = (v: VehicleFrame) =>
  (v.status === 'to_job' || v.status === 'reposition') && v.blocksToTarget > 0

export const assignmentOverlay: OverlayPlugin = {
  id: 'assignment',
  label: 'Distance to assignment',
  description: 'Route each responding vehicle still has to drive.',
  icon: Route,
  defaultOn: true,
  // Under the markers, so a route never draws across the vehicle driving it.
  under: true,
  render: {
    map2d: ({ frame, sy, px }) =>
      frame.vehicles.filter(assigned).map((v) => {
        const color = VEHICLE_STATUS[v.status].color
        return (
          <polyline key={v.id} points={toPoints(v.remainingPath, sy)} fill="none" stroke={color} strokeWidth={2.5 * px}
              strokeDasharray={`${7 * px} ${5 * px}`} strokeLinecap="round" strokeLinejoin="round"
            className="animate-[dash_1s_linear_infinite]" style={{ ['--dash' as string]: `${-12 * px}` }} />
        )
      }),
    map3d: ({ frame, heightAt }) =>
      frame.vehicles.filter(assigned).map((v) => {
        const color = VEHICLE_STATUS[v.status].color
        return <Line3D key={v.id} path={v.remainingPath} height={heightAt} color={color} width={2.5} dashed />
      }),
  },
}
