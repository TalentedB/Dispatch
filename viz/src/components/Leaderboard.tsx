import { useEffect, useMemo, useState } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { Crown, Trophy, X } from 'lucide-react'
import type { Trace } from '@/contract/trace'
import { algorithmMeta } from '@/algorithms/registry'
import { getTrace, type ScenarioEntry } from '@/data/traces'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const METRICS = [
  { key: 'avg_response', label: 'Avg response', hint: 'Mean minutes from a call coming in to its job starting' },
  { key: 'max_response', label: 'Worst response', hint: 'Longest single wait in the scenario' },
  { key: 'total_drive', label: 'Fleet driving', hint: 'Total minutes driven, including returns to base' },
] as const
type MetricKey = (typeof METRICS)[number]['key']

/** scenario id -> algorithm id -> trace, for every scenario we know about. */
function useAllTraces(scenarios: ScenarioEntry[], open: boolean) {
  const [state, setState] = useState<{ key: string; traces: Record<string, Record<string, Trace>> } | null>(null)
  const key = scenarios.map((s) => `${s.id}:${s.algorithms.join(',')}`).join('|')
  useEffect(() => {
    if (!open) return
    let live = true
    const jobs = scenarios.flatMap((s) => s.algorithms.map((a) => getTrace(s.id, a).then((t) => [s.id, a, t] as const)))
    Promise.allSettled(jobs).then((rs) => {
      if (!live) return
      const out: Record<string, Record<string, Trace>> = {}
      for (const r of rs) {
        if (r.status !== 'fulfilled') continue
        const [s, a, t] = r.value
        out[s] = { ...out[s], [a]: t }
      }
      setState({ key, traces: out })
    })
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures the scenario list
  }, [key, open])
  // null while loading; failed traces are simply left out.
  return state?.key === key ? state.traces : null
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
 * invalid schedules rank last), then across scenarios. The winner has the most wins;
 * ties go to the better average rank, then the lower total.
 */
function standings(scenarios: ScenarioEntry[], traces: Record<string, Record<string, Trace>>, metric: MetricKey) {
  const algos = [...new Set(scenarios.flatMap((s) => s.algorithms))]
  const acc = new Map<string, { wins: number; rankSum: number; n: number; total: number; invalid: number }>(
    algos.map((a) => [a, { wins: 0, rankSum: 0, n: 0, total: 0, invalid: 0 }]),
  )
  const best: Record<string, number> = {}
  for (const s of scenarios) {
    const row = traces[s.id]
    if (!row) continue
    const score = (a: string) => {
      const t = row[a]
      if (!t || t.check?.valid === false) return Infinity
      return t.metrics?.[metric] ?? Infinity
    }
    const present = s.algorithms.filter((a) => row[a])
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
    return { algo: a, wins: e.wins, avgRank: e.n ? e.rankSum / e.n : Infinity, total: e.total, invalid: e.invalid }
  })
  list.sort((x, y) => y.wins - x.wins || x.avgRank - y.avgRank || x.total - y.total)
  return { list, best, algos: list.map((s) => s.algo) }
}

const fmt = (v: number | undefined, metric: MetricKey) =>
  v === undefined || !Number.isFinite(v) ? '–' : metric === 'avg_response' ? v.toFixed(1) : Math.round(v).toString()

export function Leaderboard({ scenarios, trigger }: { scenarios: ScenarioEntry[]; trigger: React.ReactElement }) {
  const [open, setOpen] = useState(false)
  const [metric, setMetric] = useState<MetricKey>('avg_response')
  const loaded = useAllTraces(scenarios, open)
  const traces = useMemo(() => loaded ?? {}, [loaded])
  const { list, best, algos } = useMemo(() => standings(scenarios, traces, metric), [scenarios, traces, metric])
  const m = METRICS.find((x) => x.key === metric)!
  const winner = list[0]

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger render={trigger} />
      <Dialog.Portal>
        <Dialog.Backdrop className="leaderboard-backdrop" />
        <Dialog.Popup className="leaderboard">
          <header className="leaderboard-header">
            <div>
              <Dialog.Title className="leaderboard-title"><Trophy aria-hidden="true" /> Leaderboard</Dialog.Title>
              <Dialog.Description className="leaderboard-sub">
                Every algorithm on every test. Lower is better; invalid schedules rank last.
              </Dialog.Description>
            </div>
            <ToggleGroup value={[metric]} onValueChange={(v) => v[0] && setMetric(v[0] as MetricKey)}
              className="segmented" variant="default" size="sm" spacing={0}>
              {METRICS.map((x) => <ToggleGroupItem key={x.key} value={x.key} title={x.hint}>{x.label}</ToggleGroupItem>)}
            </ToggleGroup>
            <Dialog.Close render={<Button variant="ghost" size="icon-sm" aria-label="Close leaderboard" />}><X /></Dialog.Close>
          </header>

          {!loaded ? (
            <p className="leaderboard-loading" role="status">Loading {scenarios.length} tests…</p>
          ) : (
            <div className="leaderboard-body">
              <ol className="podium">
                {list.map((s, i) => {
                  const meta = algorithmMeta(s.algo)
                  return (
                    <li key={s.algo} className={cn('podium-card', i === 0 && 'is-winner')} style={{ ['--algo' as string]: meta.color }}>
                      <span className="podium-place">{i === 0 ? <Crown aria-label="Winner" /> : `#${i + 1}`}</span>
                      <span className="podium-name">{meta.label}</span>
                      <span className="podium-stats">
                        <span><strong>{s.wins}</strong> wins</span>
                        <span><strong>{s.avgRank.toFixed(2)}</strong> avg rank</span>
                        <span title={`Sum of ${m.label.toLowerCase()} over every test`}><strong>{fmt(s.total, metric)}</strong> min total</span>
                        {s.invalid > 0 && <span className="text-destructive"><strong>{s.invalid}</strong> invalid</span>}
                      </span>
                    </li>
                  )
                })}
              </ol>

              <div className="leaderboard-table-wrap">
                <table className="leaderboard-table">
                  <thead>
                    <tr>
                      <th scope="col">Test</th>
                      {algos.map((a) => <th key={a} scope="col">{algorithmMeta(a).short}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {scenarios.filter((s) => traces[s.id]).map((s) => (
                      <tr key={s.id}>
                        <th scope="row">{s.label}<span className="leaderboard-meta">{s.vehicles}v · {s.calls}c</span></th>
                        {algos.map((a) => {
                          const t = traces[s.id][a]
                          const v = t?.metrics?.[metric]
                          const invalid = t?.check?.valid === false
                          const top = !invalid && v !== undefined && v === best[s.id]
                          return (
                            <td key={a} className={cn(top && 'is-best', invalid && 'is-invalid')} title={invalid ? 'Invalid schedule' : undefined}>
                              {invalid ? '✕' : fmt(v, metric)}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {winner && (
                <p className="leaderboard-foot">
                  Winner: most tests won, then best average rank, then lowest total. Ranking by {m.label.toLowerCase()}.
                </p>
              )}
            </div>
          )}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
