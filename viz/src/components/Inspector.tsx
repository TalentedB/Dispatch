import { useEffect, useRef, useState } from 'react'
import type { Trace } from '@/contract/trace'
import { algorithmMeta } from '@/algorithms/registry'
import { CALL_STATUS, VEHICLE_STATUS } from '@/engine/status'
import { clock, clockActions, formatClock } from '@/playback/clock'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const METRICS: { key: string; label: string; unit: string; digits: number; hint: string; diagnostic?: boolean }[] = [
  { key: 'avg_response', label: 'Avg response', unit: 'min', digits: 1, hint: 'call in → job started' },
  { key: 'max_response', label: 'Worst response', unit: 'min', digits: 0, hint: 'longest single wait' },
  { key: 'avg_delay', label: 'Avg delay', unit: 'min', digits: 1, hint: 'response minus drive from base' },
  { key: 'total_drive', label: 'Fleet driving', unit: 'min', digits: 0, hint: 'incl. returns and repositioning' },
  { key: 'vehicles_used', label: 'Vehicles used', unit: '', digits: 0, hint: 'served ≥ 1 call' },
  { key: 'computation_seconds', label: 'Program runtime', unit: 's', digits: 2, hint: 'diagnostic only', diagnostic: true },
]

function Compare({ traces, panes, onPick }: { traces: Trace[]; panes: (string | null)[]; onPick: (pane: number, algo: string) => void }) {
  const sorted = [...traces].sort((a, b) => (a.metrics?.avg_response ?? Infinity) - (b.metrics?.avg_response ?? Infinity))
  return (
    <div className="comparison-list">
      <div className="inspector-intro"><h2>Algorithm comparison</h2><p>Sorted by response time. Runtime is diagnostic.</p></div>
      <div className="algorithm-choices">
        {sorted.map((t) => {
          const meta = algorithmMeta(t.algorithm.id, t.algorithm)
          return (
            <div key={t.algorithm.id} className="algorithm-row">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-xs font-semibold">
                  {meta.label}
                  {t.check && !t.check.valid && <Badge variant="destructive" className="h-4 text-xs">invalid</Badge>}
                </div>
                <div className="truncate text-xs text-muted-foreground" title={meta.description}>{meta.description}</div>
              </div>
              {panes.map((p, i) => (
                <Button key={i} size="xs" variant={p === t.algorithm.id ? 'secondary' : 'outline'} aria-pressed={p === t.algorithm.id} aria-label={`Show ${meta.label}${panes.length > 1 ? ` in ${i === 0 ? 'left' : 'right'} pane` : ''}`} onClick={() => onPick(i, t.algorithm.id)}>
                  {panes.length > 1 ? (i === 0 ? 'L' : 'R') : 'Show'}
                </Button>
              ))}
            </div>
          )
        })}
      </div>
      {METRICS.map((m) => {
        const values = sorted.map((t) => t.metrics?.[m.key]).filter((v): v is number => v !== undefined)
        const best = Math.min(...values)
        const max = Math.max(...values, 1e-9)
        return (
          <section key={m.key} className="comparison-metric">
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <span className="text-xs font-semibold whitespace-nowrap">{m.label}</span>
              <span className="metric-hint" title={m.diagnostic ? 'not part of the response objective' : 'lower is better'}>{m.hint}</span>
            </div>
            <div className="flex flex-col gap-1.5">
              {sorted.map((t) => {
                const v = t.metrics?.[m.key]
                const meta = algorithmMeta(t.algorithm.id, t.algorithm)
                return (
                  <div key={t.algorithm.id} className="flex items-center gap-2 text-xs">
                    <span className="w-20 truncate text-muted-foreground">{meta.short}</span>
                    <div className="metric-bar-track">
                      <div className="metric-bar" style={{ transform: `scaleX(${(v ?? 0) / max})`, background: meta.color, opacity: m.diagnostic ? 0.65 : v === best ? 1 : 0.45 }} />
                    </div>
                    <span className={cn('w-20 text-right whitespace-nowrap tabular-nums', !m.diagnostic && v === best && 'font-semibold text-foreground')}>
                      {v === undefined ? '–' : v.toFixed(m.digits)}{m.unit && <span className="text-muted-foreground"> {m.unit}</span>}
                    </span>
                  </div>
                )
              })}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function Log({ trace }: { trace: Trace | null }) {
  const t = clock.use((s) => Math.floor(s.time))
  const lines = trace?.log ?? []
  const current = lines.findLastIndex((l) => l.time <= t)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    ref.current?.querySelector(`[data-i="${current}"]`)?.scrollIntoView({ block: 'center' })
  }, [current])
  if (!lines.length) return <p className="text-xs text-muted-foreground">No output log in this trace.</p>
  return (
    <div ref={ref} className="event-log">
      {lines.map((l, i) => (
        <button key={i} data-i={i} onClick={() => clockActions.seek(l.time)}
          className={cn('log-line', l.time > t && 'is-future', i === current && 'is-current')}>
          <span className="text-muted-foreground">{formatClock(l.time)}</span>
          <span className="font-semibold">V{l.vehicle}</span>
          <span className="truncate">{l.text.replace(/^Vehicle\s+\d+:\s*\d+:\d+\s*/i, '')}</span>
        </button>
      ))}
    </div>
  )
}

function Legend() {
  return (
    <div className="flex flex-col gap-4 text-xs">
      <section>
        <h4 className="mb-2 font-semibold">Vehicle state</h4>
        {Object.entries(VEHICLE_STATUS).map(([k, s]) => (
          <div key={k} className="flex items-center gap-2 py-0.5">
            <span className="size-3 rounded-full border-2" style={{ borderColor: s.color }} />
            <span>{s.label}</span>
            <code className="ml-auto text-xs text-muted-foreground">{k}</code>
          </div>
        ))}
      </section>
      <section>
        <h4 className="mb-2 font-semibold">Emergency</h4>
        {Object.entries(CALL_STATUS).map(([k, s]) => (
          <div key={k} className="flex items-center gap-2 py-0.5">
            <span className="size-2.5 rotate-45 rounded-[2px]" style={{ background: s.color }} />
            <span>{s.label}</span>
          </div>
        ))}
      </section>
      <section className="legend-section text-muted-foreground">
        <h4 className="mb-1 font-semibold text-foreground">Shortcuts</h4>
        <dl className="shortcut-list"><dt>Play / pause</dt><dd><kbd>Space</kbd></dd><dt>Step one minute</dt><dd><kbd>← / →</kbd></dd><dt>Step ten minutes</dt><dd><kbd>Shift + ← / →</kbd></dd><dt>Playback speed</dt><dd><kbd>[ / ]</kbd></dd><dt>Start / end</dt><dd><kbd>Home / End</kbd></dd></dl>
      </section>
      <section className="legend-section text-muted-foreground">
        <h4 className="mb-1 font-semibold text-foreground">Add an algorithm</h4>
        <p>Register it in <code>solvers.txt</code> and run <code>python3 tools/export_viz.py</code>, or drop a
          <code> uvec.trace/v1</code> JSON file anywhere on this page. See <code>viz/README.md</code>.</p>
      </section>
    </div>
  )
}

export function Inspector({ traces, logTrace, panes, onPick }: {
  traces: Trace[]; logTrace: Trace | null; panes: (string | null)[]; onPick: (pane: number, algo: string) => void
}) {
  const [tab, setTab] = useState('compare')
  return (
    <Tabs value={tab} onValueChange={(v) => setTab(v as string)} className="inspector-tabs">
      <TabsList className="inspector-tab-list" aria-label="Inspector sections">
        <TabsTrigger value="compare">Compare</TabsTrigger>
        <TabsTrigger value="log">Log</TabsTrigger>
        <TabsTrigger value="legend">Legend</TabsTrigger>
      </TabsList>
      <ScrollArea className="min-h-0 flex-1">
        <div className="inspector-content">
          <TabsContent value="compare"><Compare traces={traces} panes={panes} onPick={onPick} /></TabsContent>
          <TabsContent value="log">{tab === 'log' && <Log trace={logTrace} />}</TabsContent>
          <TabsContent value="legend"><Legend /></TabsContent>
        </div>
      </ScrollArea>
    </Tabs>
  )
}
