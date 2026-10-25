import { Spline } from 'lucide-react'
import { trail } from '@/engine/sample'
import { vehicleColor } from '@/engine/status'
import { Line3D, toPoints } from './shared'
import type { OverlayPlugin } from './types'

const WINDOW = 45 // minutes of history

export const trailsOverlay: OverlayPlugin = {
  id: 'trails',
  label: 'Trails',
  description: `Where each vehicle drove in the last ${WINDOW} minutes.`,
  icon: Spline,
  defaultOn: false,
  under: true,
  render: {
    map2d: ({ prepared, frame, sy, px }) =>
      prepared.trace.vehicles.map((v, i) => {
        const path = trail(prepared, i, frame.t, WINDOW)
        return path.length > 1 && (
          <polyline key={v.id} points={toPoints(path, sy)} fill="none" stroke={vehicleColor(v.id)}
            strokeWidth={4 * px} strokeOpacity={0.35} strokeLinecap="round" strokeLinejoin="round" />
        )
      }),
    map3d: ({ prepared, frame, heightAt }) =>
      prepared.trace.vehicles.map((v, i) => (
        <Line3D key={v.id} path={trail(prepared, i, frame.t, WINDOW)} height={heightAt} color={vehicleColor(v.id)} width={3} opacity={0.5} />
      )),
  },
}
