import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import type { Frame, Prepared } from '@/engine/sample'
import type { OverlaySlot } from '@/views/types'

/** What every overlay layer receives. Map slots add a projection helper. */
export interface OverlayContext {
  prepared: Prepared
  frame: Frame
}

export interface Map2DContext extends OverlayContext {
  /** Grid y -> screen y (north up). */
  sy: (y: number) => number
  /** Size of one screen pixel in grid units, for zoom-independent strokes and text. */
  px: number
}

export interface Map3DContext extends OverlayContext {
  /** Terrain height at a grid point, so overlays sit on the surface. */
  heightAt: (x: number, y: number) => number
}

export interface GanttContext extends OverlayContext {
  tx: (t: number) => number
  laneY: (vehicle: number) => number
  laneH: number
}

/**
 * A toggleable layer. Implement one renderer per slot it supports; views that
 * host that slot pick it up automatically. Register it in overlays/registry.ts.
 */
export interface OverlayPlugin {
  id: string
  label: string
  description: string
  icon: LucideIcon
  defaultOn: boolean
  /** Draw beneath vehicles and calls (heatmaps, trails). */
  under?: boolean
  render: Partial<{
    map2d: (ctx: Map2DContext) => ReactNode
    map3d: (ctx: Map3DContext) => ReactNode
    gantt: (ctx: GanttContext) => ReactNode
  }>
}

export function supports(o: OverlayPlugin, slot: OverlaySlot) {
  return o.render[slot] !== undefined
}
