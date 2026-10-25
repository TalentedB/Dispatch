import type { ComponentType } from 'react'
import type { LucideIcon } from 'lucide-react'
import type { Frame, Prepared } from '@/engine/sample'

/**
 * A view renders one trace at the current clock time. Register it in views/registry.ts.
 *
 * `slot` says which kind of overlay layers the view can host (see overlays/types.ts);
 * the pane only offers overlays that implement that slot.
 */
export type OverlaySlot = 'map2d' | 'map3d' | 'gantt'

export interface ViewOption {
  id: string
  label: string
  choices: { value: string; label: string }[]
  default: string
}

export interface ViewProps {
  prepared: Prepared
  frame: Frame
  /** Enabled overlay ids for this pane. */
  overlays: Set<string>
  /** Values of the view's own options. */
  options: Record<string, string>
  accent: string
}

export interface ViewPlugin {
  id: string
  label: string
  icon: LucideIcon
  slot: OverlaySlot
  options?: ViewOption[]
  component: ComponentType<ViewProps>
}
