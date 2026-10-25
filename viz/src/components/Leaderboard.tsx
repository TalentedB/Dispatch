import { useEffect, useMemo, useState } from 'react'
import { Dialog } from '@base-ui/react/dialog'
import { Crown, Trophy, X } from 'lucide-react'
import type { Trace } from '@/contract/trace'
import { algorithmMeta } from '@/algorithms/registry'
import { getTrace, type ScenarioEntry } from '@/data/traces'
import { cn } from '@/lib/utils'
import { metricValue, standings, type MetricKey } from '@/engine/leaderboard'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'

const METRICS = [
  { key: 'total_wait', label: 'Total wait', hint: 'Sum of all report-to-service waits; lowest combined total wins' },
  { key: 'avg_response', label: 'Avg response', hint: 'Mean minutes from a call coming in to its job starting' },
  { key: 'max_response', label: 'Worst response', hint: 'Longest single wait in the scenario' },
  { key: 'total_drive', label: 'Fleet driving', hint: 'Total minutes driven, including returns to base' },
] as const

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

const fmt = (v: number | undefined, metric: MetricKey) =>
  v === undefined || !Number.isFinite(v) ? '–' : metric === 'avg_response' ? v.toFixed(1) : Math.round(v).toString()

export function Leaderboard({ scenarios, trigger }: { scenarios: ScenarioEntry[]; trigger: React.ReactElement }) {
  const [open, setOpen] = useState(false)
  const [metric, setMetric] = useState<MetricKey>('total_wait')
  const loaded = useAllTraces(scenarios, open)
  const traces = useMemo(() => loaded ?? {}, [loaded])
  const { list, best, algos } = useMemo(() => standings(scenarios, traces, metric), [scenarios, traces, metric])
  const m = METRICS.find((x) => x.key === metric)!
  const winner = list.find((entry) => metric !== 'total_wait' || Number.isFinite(entry.total))

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
                {metric === 'total_wait'
                  ? 'Emergency waits summed across every test. Lowest complete total wins.'
                  : 'Every algorithm on every test. Lower is better; invalid schedules rank last.'}
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
                    <li key={s.algo} className={cn('podium-card', s === winner && 'is-winner')} style={{ ['--algo' as string]: meta.color }}>
                      <span className="podium-place">{s === winner ? <Crown aria-label="Winner" /> : `#${i + 1}`}</span>
                      <span className="podium-name">{meta.label}</span>
                      <span className="podium-stats">
                        {metric !== 'total_wait' && <span><strong>{s.wins}</strong> wins</span>}
                        {metric !== 'total_wait' && <span><strong>{s.avgRank.toFixed(2)}</strong> avg rank</span>}
                        <span title={`Sum of ${m.label.toLowerCase()} over every test`}><strong>{fmt(s.total, metric)}</strong> min {metric === 'total_wait' ? 'waiting' : 'total'}</span>
                        {s.invalid > 0 && <span className="text-destructive"><strong>{s.invalid}</strong> {metric === 'total_wait' ? 'missing or invalid tests' : 'invalid'}</span>}
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
                          const v = metricValue(t, metric)
                          const invalid = t?.check?.valid === false || (metric === 'total_wait' && !Number.isFinite(v))
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
                  {metric === 'total_wait'
                    ? 'Winner: lowest sum of report-to-service wait across all emergencies in all tests. Missing or invalid tests disqualify an overall total.'
                    : `Winner: most tests won, then best average rank, then lowest total. Ranking by ${m.label.toLowerCase()}.`}
                </p>
              )}
            </div>
          )}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
