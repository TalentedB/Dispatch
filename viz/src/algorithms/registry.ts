import { themeColor } from '@/lib/theme'
/**
 * Display metadata for algorithms. Optional: an algorithm with no entry here still
 * works (it gets its id as a label and a generated colour). Add an entry when you
 * add a solver to solvers.txt to give it a nicer name and description.
 */

export interface AlgorithmMeta {
  id: string
  label: string
  short: string
  description: string
  color: string
}

const KNOWN: Record<string, Omit<AlgorithmMeta, 'id'>> = {
  strategy4: {
    label: 'Strategy 4: adaptive hybrid',
    short: 'Strategy 4',
    description: 'Online DP/MILP scheduling with locked emergency commitments and adaptive resting coverage. Only reported calls inform decisions.',
    color: themeColor('series-5'),
  },
  milp: {
    label: 'Hybrid DP/MILP, base deployment',
    short: 'Hybrid base',
    description: 'Optimizes known queued calls with exact small-queue DP or time-limited MILP. Returns idle vehicles to base.',
    color: themeColor('series-6'),
  },
  dispatch_greedy: {
    label: 'Dispatch greedy, base deployment',
    short: 'Dispatch greedy',
    description: 'Earliest-arrival baseline using the hybrid scheduler’s event-driven simulator, with base returns.',
    color: themeColor('series-1'),
  },
  greedy: {
    label: 'Greedy earliest arrival',
    short: 'Greedy',
    description: 'Each call goes to the vehicle that can arrive soonest, including busy ones (the job is chained).',
    color: themeColor('series-1'),
  },
  closest_idle: {
    label: 'Closest idle, FCFS',
    short: 'Closest idle',
    description: 'Nearest free vehicle. If none is free, calls wait and are served oldest-first.',
    color: themeColor('series-2'),
  },
  nearest_neighbor: {
    label: 'Nearest neighbour',
    short: 'Nearest nbr',
    description: 'Nearest free vehicle. A vehicle that frees up takes the closest waiting call.',
    color: themeColor('series-3'),
  },
  hungarian: {
    label: 'Hungarian matching',
    short: 'Hungarian',
    description: 'Free vehicles and waiting calls are matched to minimise total distance (Kuhn-Munkres).',
    color: themeColor('series-4'),
  },
}

/** Labels/descriptions carried by traces themselves (e.g. uploaded files). */
const fromTraces: Record<string, { label?: string; description?: string }> = {}

export function registerAlgorithm(id: string, meta: { label?: string; description?: string }) {
  if (meta.label || meta.description) fromTraces[id] = { ...fromTraces[id], ...meta }
}

function hashColor(id: string): string {
  let h = 0
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return themeColor(`series-${(h % 6) + 1}`)
}

export function algorithmMeta(id: string, fromTrace?: { label?: string; description?: string }): AlgorithmMeta {
  const known = KNOWN[id]
  fromTrace = { ...fromTraces[id], ...fromTrace }
  return {
    id,
    label: fromTrace?.label ?? known?.label ?? id.replace(/_/g, ' '),
    short: known?.short ?? fromTrace?.label ?? id.replace(/_/g, ' '),
    description: fromTrace?.description ?? known?.description ?? 'No description provided.',
    color: known?.color ?? hashColor(id),
  }
}
