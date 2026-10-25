import type { SegmentKind } from '@/contract/trace'

/** Display info for each vehicle state. A new SegmentKind only needs an entry here. */
export const VEHICLE_STATUS: Record<SegmentKind, { label: string; short: string; color: string }> = {
  idle: { label: 'Idle', short: 'IDLE', color: '#94a3b8' },
  to_job: { label: 'Responding to emergency', short: 'EN ROUTE', color: '#f59e0b' },
  on_job: { label: 'Attending emergency', short: 'ON SCENE', color: '#f43f5e' },
  to_base: { label: 'Returning to base', short: 'RETURNING', color: '#38bdf8' },
  reposition: { label: 'Moving to standby point', short: 'REPOSITION', color: '#a78bfa' },
}

export type CallStatus = 'future' | 'waiting' | 'dispatched' | 'on_scene' | 'done'

export const CALL_STATUS: Record<CallStatus, { label: string; color: string }> = {
  future: { label: 'Not yet called in', color: '#64748b' },
  waiting: { label: 'Waiting for a vehicle', color: '#ef4444' },
  dispatched: { label: 'Vehicle en route', color: '#f59e0b' },
  on_scene: { label: 'Being attended', color: '#f43f5e' },
  done: { label: 'Resolved', color: '#22c55e' },
}

const VEHICLE_PALETTE = [
  '#60a5fa', '#f472b6', '#34d399', '#fbbf24', '#a78bfa',
  '#fb923c', '#22d3ee', '#a3e635', '#e879f9', '#f87171',
  '#2dd4bf', '#facc15',
]

export function vehicleColor(id: number): string {
  return VEHICLE_PALETTE[id % VEHICLE_PALETTE.length]
}
