import { ganttView } from './GanttView'
import { isometricView } from './IsometricView'
import { topDownView } from './TopDownView'
import type { ViewPlugin } from './types'

/** Every view, in switcher order. Add a new one here. */
export const VIEWS: ViewPlugin[] = [topDownView, isometricView, ganttView]

export const viewById = (id: string) => VIEWS.find((v) => v.id === id) ?? VIEWS[0]
