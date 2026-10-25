import { themeColor } from '@/lib/theme'
import type { SegmentKind } from '@/contract/trace'

/** Display info for each vehicle state. A new SegmentKind only needs an entry here. */
export const VEHICLE_STATUS: Record<SegmentKind, { label: string; short: string; color: string }> = {
  idle: { label: 'Idle', short: 'Idle', color: themeColor('state-idle') },
  to_job: { label: 'Responding to emergency', short: 'En route', color: themeColor('state-travel') },
  on_job: { label: 'Attending emergency', short: 'On scene', color: themeColor('state-scene') },
  to_base: { label: 'Returning to base', short: 'Returning', color: themeColor('state-return') },
  reposition: { label: 'Moving to standby point', short: 'Repositioning', color: themeColor('state-reposition') },
}

export type CallStatus = 'future' | 'waiting' | 'dispatched' | 'on_scene' | 'done'

export const CALL_STATUS: Record<CallStatus, { label: string; color: string }> = {
  future: { label: 'Not yet called in', color: themeColor('state-idle') },
  waiting: { label: 'Waiting for a vehicle', color: themeColor('state-scene') },
  dispatched: { label: 'Vehicle en route', color: themeColor('state-travel') },
  on_scene: { label: 'Being attended', color: themeColor('state-scene') },
  done: { label: 'Resolved', color: themeColor('state-done') },
}

const VEHICLE_PALETTE = Array.from({ length: 6 }, (_, i) => themeColor(`series-${i + 1}`))

export function vehicleColor(id: number): string {
  return VEHICLE_PALETTE[id % VEHICLE_PALETTE.length]
}
