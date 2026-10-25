import { CalendarClock } from 'lucide-react'
import { CALL_STATUS } from '@/engine/status'
import { formatMinutes } from '@/playback/clock'
import { Pill } from './shared'
import type { OverlayPlugin } from './types'

const HORIZON = 60

export const futureOverlay: OverlayPlugin = {
  id: 'future',
  label: 'Upcoming calls',
  description: `Ghosts of calls coming in within ${HORIZON} minutes. The algorithms can't see these (dispatch is online).`,
  icon: CalendarClock,
  defaultOn: false,
  render: {
    map2d: ({ frame, sy, px }) =>
      frame.calls
        .filter((c) => c.status === 'future' && c.call.time - frame.t <= HORIZON)
        .map((c) => (
          <g key={c.call.id} opacity={1 - (c.call.time - frame.t) / HORIZON / 1.4}>
            <circle cx={c.call.x} cy={sy(c.call.y)} r={7 * px} fill="none" stroke={CALL_STATUS.future.color}
              strokeWidth={1.5 * px} strokeDasharray={`${3 * px} ${2 * px}`} />
            <Pill x={c.call.x} y={sy(c.call.y)} dy={-16} px={px} text={`in ${formatMinutes(c.call.time - frame.t)}`} color={CALL_STATUS.future.color} />
          </g>
        )),
    map3d: ({ frame, heightAt }) =>
      frame.calls
        .filter((c) => c.status === 'future' && c.call.time - frame.t <= HORIZON)
        .map((c) => (
          <mesh key={c.call.id} position={[c.call.x, heightAt(c.call.x, c.call.y) + 0.6, -c.call.y]}>
            <octahedronGeometry args={[0.45]} />
            <meshBasicMaterial color={CALL_STATUS.future.color} wireframe />
          </mesh>
        )),
  },
}
