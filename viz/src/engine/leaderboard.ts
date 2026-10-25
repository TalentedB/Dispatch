import type { Trace } from '../contract/trace.ts'
import type { ScenarioEntry } from '@/data/traces'

export type MetricKey = 'total_wait' | 'avg_response' | 'max_response' | 'total_drive'

/** Sum individual call waits; never reconstruct totals from rounded averages. */
export function totalEmergencyWait(trace: Trace): number {
  if (trace.check?.valid === false) return Infinity
  const starts = new Map<number, number>()
  for (const vehicle of trace.vehicles) {
    for (const segment of vehicle.segments) {
      if (segment.kind !== 'on_job') continue
      if (segment.callId === undefined || starts.has(segment.callId)) return Infinity
      starts.set(segment.callId, segment.start)
    }
  }
  if (starts.size !== trace.calls.length) return Infinity
  let total = 0
  for (const call of trace.calls) {
    const start = starts.get(call.id)
    if (start === undefined || !Number.isFinite(start) || start < call.time) return Infinity
    total += start - call.time
  }
  return total
}

export function metricValue(trace: Trace | undefined, metric: MetricKey): number {
  if (!trace || trace.check?.valid === false) return Infinity
  return metric === 'total_wait' ? totalEmergencyWait(trace) : trace.metrics?.[metric] ?? Infinity
}

interface Standing {
  algo: string
  wins: number
  avgRank: number
  total: number
  invalid: number
}

/**
 * Rank algorithms within each scenario (lower metric is better, ties share the rank,
 * invalid schedules rank last), then across scenarios. Total wait ranks by the
 * complete sum; other metrics retain the wins / average rank / total ordering.
 */
export function standings(scenarios: ScenarioEntry[], traces: Record<string, Record<string, Trace>>, metric: MetricKey) {
  const algos = [...new Set(scenarios.flatMap((s) => s.algorithms))]
  const acc = new Map<string, { wins: number; rankSum: number; n: number; total: number; invalid: number }>(
    algos.map((a) => [a, { wins: 0, rankSum: 0, n: 0, total: 0, invalid: 0 }]),
  )
  const best: Record<string, number> = {}
  for (const s of scenarios) {
    const row = traces[s.id]
    if (!row && metric !== 'total_wait') continue
    const score = (a: string) => metricValue(row?.[a], metric)
    const present = metric === 'total_wait' ? algos : s.algorithms.filter((a) => row[a])
    const values = present.map(score)
    best[s.id] = Math.min(...values)
    for (const a of present) {
      const v = score(a)
      const e = acc.get(a)!
      const rank = 1 + values.filter((o) => o < v).length
      e.rankSum += rank
      e.n++
      if (v === best[s.id] && v !== Infinity) e.wins++
      if (v !== Infinity) e.total += v
      else e.invalid++
    }
  }
  const list: Standing[] = algos.map((a) => {
    const e = acc.get(a)!
    return { algo: a, wins: e.wins, avgRank: e.n ? e.rankSum / e.n : Infinity, total: metric === 'total_wait' && e.invalid ? Infinity : e.total, invalid: e.invalid }
  })
  list.sort((x, y) => metric === 'total_wait'
    ? x.total - y.total || x.invalid - y.invalid || x.algo.localeCompare(y.algo)
    : y.wins - x.wins || x.avgRank - y.avgRank || x.total - y.total)
  return { list, best, algos: list.map((s) => s.algo) }
}

