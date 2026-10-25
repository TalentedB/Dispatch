import { useId, useMemo } from 'react'
import { AlertTriangle, CheckCircle2, Layers, Loader2 } from 'lucide-react'
import type { Trace } from '@/contract/trace'
import { algorithmMeta } from '@/algorithms/registry'
import { prepare, sampleFrame } from '@/engine/sample'
import { CALL_STATUS } from '@/engine/status'
import { OVERLAYS } from '@/overlays/registry'
import { supports } from '@/overlays/types'
import { clock, formatMinutes } from '@/playback/clock'
import { VIEWS, viewById } from '@/views/registry'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export interface PaneState {
  algorithm: string | null
  view: string
  overlays: Set<string>
  options: Record<string, Record<string, string>> // view id -> option id -> value
}

interface Props {
  state: PaneState
  onChange: (patch: Partial<PaneState>) => void
  algorithms: string[]
  trace: Trace | null
  error: string | null
}

export function Pane({ state, onChange, algorithms, trace, error }: Props) {
  const view = viewById(state.view)
  const meta = algorithmMeta(state.algorithm ?? '', trace?.algorithm)
  const options = Object.fromEntries((view.options ?? []).map((o) => [o.id, state.options[view.id]?.[o.id] ?? o.default]))
  const available = OVERLAYS.filter((o) => supports(o, view.slot))
  const uid = useId()

  return (
    <section className="simulation-pane" aria-label={`${meta.label} simulation`}>
      <div className="pane-toolbar">
        <Select
          value={state.algorithm}
          onValueChange={(v) => onChange({ algorithm: v })}
          items={Object.fromEntries(algorithms.map((a) => [a, algorithmMeta(a).label]))}
        >
          <SelectTrigger size="sm" className="algorithm-select" aria-label="Algorithm">
            <SelectValue placeholder="Algorithm" />
          </SelectTrigger>
          <SelectContent>
            {algorithms.map((a) => {
              const m = algorithmMeta(a)
              return (
                <SelectItem key={a} value={a}>
                  {m.label}
                </SelectItem>
              )
            })}
          </SelectContent>
        </Select>

        <ToggleGroup className="view-switcher segmented" value={[view.id]} onValueChange={(v) => v[0] && onChange({ view: v[0] as string })} variant="default" size="sm" spacing={0}>
          {VIEWS.map((v) => (
            <Tooltip key={v.id}>
              <TooltipTrigger render={<ToggleGroupItem value={v.id} aria-label={v.label} />}>
                <v.icon /><span className="view-label">{v.label}</span>
              </TooltipTrigger>
              <TooltipContent>{v.label}</TooltipContent>
            </Tooltip>
          ))}
        </ToggleGroup>

        {view.options?.map((o) => (
          <Select key={o.id} value={options[o.id]}
            onValueChange={(v) => v && onChange({ options: { ...state.options, [view.id]: { ...options, [o.id]: v } } })}
            items={Object.fromEntries(o.choices.map((c) => [c.value, c.label]))}>
            <SelectTrigger size="sm" className="text-xs" aria-label={o.label}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {o.choices.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
            </SelectContent>
          </Select>
        ))}

        <Popover>
          <PopoverTrigger render={<Button variant="outline" size="sm" />}>
            <Layers /> Layers
            <Badge variant="secondary" className="ml-0.5 h-4 px-1.5 text-xs">
              {available.filter((o) => state.overlays.has(o.id)).length}
            </Badge>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80">
            <PopoverHeader>
              <PopoverTitle>{view.label} layers</PopoverTitle>
              <PopoverDescription>Toggle information layers for this pane.</PopoverDescription>
            </PopoverHeader>
            <div className="flex flex-col gap-3">
              {available.map((o) => (
                <div key={o.id} className="flex items-start gap-3">
                  <o.icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <div className="flex-1">
                    <Label htmlFor={`${uid}-${o.id}`} className="text-sm">{o.label}</Label>
                    <p className="text-xs text-muted-foreground">{o.description}</p>
                  </div>
                  <Switch id={`${uid}-${o.id}`} checked={state.overlays.has(o.id)}
                    onCheckedChange={(on) => {
                      const next = new Set(state.overlays)
                      if (on) next.add(o.id)
                      else next.delete(o.id)
                      onChange({ overlays: next })
                    }} />
                </div>
              ))}
              {available.length === 0 && <p className="text-xs text-muted-foreground">This view has no overlays.</p>}
            </div>
          </PopoverContent>
        </Popover>

        <div className="ml-auto">
          {trace?.check && (
            <Tooltip>
              <TooltipTrigger render={<span />}>
                {trace.check.valid ? (
                  <Badge variant="outline" className="valid-badge"><CheckCircle2 /> Valid schedule</Badge>
                ) : (
                  <Badge variant="destructive"><AlertTriangle /> {trace.check.errors.length} errors</Badge>
                )}
              </TooltipTrigger>
              <TooltipContent className="max-w-md">
                {trace.check.valid ? 'Passed every rule in tester/checker.py' : trace.check.errors.slice(0, 5).join('\n')}
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>

      <div className="pane-canvas">
        {trace ? (
          <PaneBody trace={trace} state={state} options={options} accent={meta.color} />
        ) : (
          <div className="absolute inset-0 grid place-items-center text-sm text-muted-foreground">
            {error ? <span role="alert" className="text-destructive">{error}</span> : <span role="status" className="loading-state"><Loader2 className="animate-spin" /> Loading simulation…</span>}
          </div>
        )}
      </div>
    </section>
  )
}

function PaneBody({ trace, state, options, accent }: { trace: Trace; state: PaneState; options: Record<string, string>; accent: string }) {
  const t = clock.use((s) => s.time)
  const prepared = prepare(trace)
  const frame = useMemo(() => sampleFrame(prepared, t), [prepared, t])
  const View = viewById(state.view).component
  const s = frame.stats
  const total = trace.calls.length
  return (
    <>
      <div className="relative min-h-0 flex-1">
        <View prepared={prepared} frame={frame} overlays={state.overlays} options={options} accent={accent} />
      </div>
      <div className="pane-stats">
        <Stat label="waiting" value={s.waiting} color={CALL_STATUS.waiting.color} pulse={s.waiting > 0} />
        <Stat label="en route" value={s.enRoute} color={CALL_STATUS.dispatched.color} />
        <Stat label="on scene" value={s.onScene} color={CALL_STATUS.on_scene.color} />
        <Stat label="resolved" value={`${s.done}/${total}`} color={CALL_STATUS.done.color} />
        <span className="flex-1" />
        <Stat label="busy" value={`${s.busy}/${trace.vehicles.length}`} color="var(--color-muted)" />
        <Stat label="avg response" value={s.avgResponse === null ? '–' : formatMinutes(s.avgResponse)} color={accent} />
      </div>
    </>
  )
}

function Stat({ label, value }: { label: string; value: string | number; color: string; pulse?: boolean }) {
  return (
    <div className="pane-stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}
