import { assignmentOverlay } from './assignment'
import { coverageOverlay } from './coverage'
import { etaOverlay } from './eta'
import { futureOverlay } from './future'
import { statusOverlay } from './status'
import { trailsOverlay } from './trails'
import type { OverlayPlugin } from './types'

/** Every toggleable overlay, in menu order. Add a new one here. */
export const OVERLAYS: OverlayPlugin[] = [
  statusOverlay,
  assignmentOverlay,
  etaOverlay,
  trailsOverlay,
  coverageOverlay,
  futureOverlay,
]

export const DEFAULT_OVERLAYS = new Set(OVERLAYS.filter((o) => o.defaultOn).map((o) => o.id))
