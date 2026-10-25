import { useEffect, useMemo, useRef, useState } from 'react'
import { Ambulance, Columns2, PanelRight, Square, Upload } from 'lucide-react'
import { DEFAULT_OVERLAYS } from '@/overlays/registry'
import { addTraceFiles, dataStore, loadManifest, useScenarioTraces, useScenarios, useTrace } from '@/data/traces'
import { clockActions, useClockDriver } from '@/playback/clock'
import { Pane, type PaneState } from '@/components/Pane'
import { Transport } from '@/components/Transport'
import { Inspector } from '@/components/Inspector'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { TooltipProvider } from '@/components/ui/tooltip'

const newPane = (view: string): PaneState => ({ algorithm: null, view, overlays: new Set(DEFAULT_OVERLAYS), options: {} })
const GROUP_ORDER = ['brief', 'custom', 'uploaded', 'generated']

function useKeyboard() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (el.closest('input, textarea, [role="listbox"], [role="slider"]')) return
      const big = e.shiftKey ? 10 : 1
      const keys: Record<string, () => void> = {
        ' ': clockActions.toggle,
        ArrowLeft: () => clockActions.step(-big),
        ArrowRight: () => clockActions.step(big),
        '[': clockActions.slower,
        ']': clockActions.faster,
        Home: () => clockActions.seek(-Infinity),
        End: () => clockActions.seek(Infinity),
      }
      if (keys[e.key]) {
        e.preventDefault()
        keys[e.key]()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}

export default function App() {
  useClockDriver()
  useKeyboard()
  useEffect(() => void loadManifest(), [])

  const scenarios = useScenarios()
  const loadError = dataStore.use((s) => s.error)
  const [scenarioId, setScenarioId] = useState<string | null>(null)
  const [split, setSplit] = useState(false)
  const [inspector, setInspector] = useState(true)
  const [panes, setPanes] = useState<PaneState[]>([newPane('topdown'), newPane('isometric')])
  const [notice, setNotice] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const scenario = scenarios.find((s) => s.id === scenarioId)
  useEffect(() => {
    if (!scenario && scenarios.length) setScenarioId((scenarios.find((s) => s.id === 'brief_2_vehicles') ?? scenarios[0]).id)
  }, [scenario, scenarios])

  // Keep each pane on an algorithm this scenario actually has.
  useEffect(() => {
    if (!scenario) return
    setPanes((ps) => {
      const algos = scenario.algorithms
      const fixed = ps.map((p, i) => (p.algorithm && algos.includes(p.algorithm) ? p : { ...p, algorithm: algos[i % algos.length] ?? null }))
      return fixed.some((p, i) => p !== ps[i]) ? fixed : ps
    })
  }, [scenario])

  const a = useTrace(scenario?.id ?? null, panes[0].algorithm)
  const b = useTrace(split ? (scenario?.id ?? null) : null, panes[1].algorithm)
  const visible = useMemo(() => [a.trace, split ? b.trace : null].filter((t) => t !== null), [a.trace, b.trace, split])
  const all = useScenarioTraces(scenario)

  useEffect(() => {
    if (!visible.length) return
    clockActions.setSpan({
      start: Math.min(...visible.map((t) => t.span.start)),
      end: Math.max(...visible.map((t) => t.span.end)),
    })
  }, [visible])

  const update = (i: number) => (patch: Partial<PaneState>) => setPanes((ps) => ps.map((p, j) => (j === i ? { ...p, ...patch } : p)))

  const addFiles = async (files: FileList | File[]) => {
    const { added, errors } = await addTraceFiles(files)
    if (added.length) setScenarioId(added[0].scenario.id)
    setNotice(errors.length ? errors.join(' · ') : `Loaded ${added.length} trace${added.length === 1 ? '' : 's'}`)
    setTimeout(() => setNotice(null), 5000)
  }

  const groups = GROUP_ORDER.map((g) => [g, scenarios.filter((s) => s.group === g)] as const).filter(([, s]) => s.length)

  return (
    <TooltipProvider delay={300}>
      <div className="dark flex h-screen flex-col bg-background text-foreground"
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={(e) => e.currentTarget === e.target && setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); void addFiles(e.dataTransfer.files) }}>
        <header className="flex items-center gap-3 border-b bg-zinc-950/80 px-4 py-2.5 backdrop-blur">
          <div className="flex items-center gap-2">
            <div className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-rose-500 to-amber-400 shadow-[0_0_20px] shadow-rose-500/30">
              <Ambulance className="size-4.5 text-zinc-950" />
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold">Dispatch Visualizer</div>
              <div className="text-[10px] text-muted-foreground">UVEC 2026 · emergency fleet scheduling</div>
            </div>
          </div>

          <Select value={scenario?.id ?? null} onValueChange={(v) => v && setScenarioId(v)}
            items={Object.fromEntries(scenarios.map((s) => [s.id, s.label]))}>
            <SelectTrigger className="ml-4 min-w-56">
              <SelectValue placeholder="Scenario" />
            </SelectTrigger>
            <SelectContent>
              {groups.map(([g, list]) => (
                <SelectGroup key={g}>
                  <SelectLabel className="capitalize">{g}</SelectLabel>
                  {list.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.label}
                      <span className="ml-auto pl-3 text-[10px] text-muted-foreground">{s.vehicles} veh · {s.calls} calls</span>
                    </SelectItem>
                  ))}
                </SelectGroup>
              ))}
            </SelectContent>
          </Select>
          {scenario && (
            <div className="flex gap-1.5">
              <Badge variant="secondary">{scenario.vehicles} vehicles</Badge>
              <Badge variant="secondary">{scenario.calls} calls</Badge>
            </div>
          )}

          <div className="ml-auto flex items-center gap-2">
            {notice && <span className="max-w-96 truncate text-xs text-muted-foreground">{notice}</span>}
            <Button variant="outline" size="sm" onClick={() => fileInput.current?.click()}>
              <Upload /> Load trace
            </Button>
            <input ref={fileInput} type="file" accept=".json,application/json" multiple hidden
              onChange={(e) => e.target.files && void addFiles(e.target.files)} />
            <ToggleGroup value={[split ? 'split' : 'single']} onValueChange={(v) => v[0] && setSplit(v[0] === 'split')}
              variant="outline" size="sm" spacing={0}>
              <ToggleGroupItem value="single" aria-label="Single view"><Square /> Single</ToggleGroupItem>
              <ToggleGroupItem value="split" aria-label="Side by side"><Columns2 /> Side by side</ToggleGroupItem>
            </ToggleGroup>
            <Button variant={inspector ? 'secondary' : 'ghost'} size="icon-sm" onClick={() => setInspector(!inspector)} aria-label="Toggle inspector">
              <PanelRight />
            </Button>
          </div>
        </header>

        {loadError && <div className="border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-sm text-destructive">{loadError}</div>}

        <main className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 gap-2 p-2">
            {scenario && (
              <>
                <Pane state={panes[0]} onChange={update(0)} algorithms={scenario.algorithms} trace={a.trace} error={a.error} />
                {split && <Pane state={panes[1]} onChange={update(1)} algorithms={scenario.algorithms} trace={b.trace} error={b.error} />}
              </>
            )}
          </div>
          {inspector && (
            <aside className="w-80 shrink-0 border-l bg-zinc-950/40">
              <Inspector traces={all} logTrace={a.trace} panes={split ? [panes[0].algorithm, panes[1].algorithm] : [panes[0].algorithm]}
                onPick={(i, algo) => update(i)({ algorithm: algo })} />
            </aside>
          )}
        </main>

        <Transport traces={visible} />

        {dragging && (
          <div className="pointer-events-none fixed inset-0 z-50 grid place-items-center bg-zinc-950/70 backdrop-blur-sm">
            <div className="rounded-2xl border-2 border-dashed border-zinc-500 px-10 py-8 text-center">
              <Upload className="mx-auto mb-2 size-8" />
              <div className="font-semibold">Drop uvec.trace/v1 JSON files</div>
              <div className="text-xs text-muted-foreground">They'll be added as algorithms on their scenario</div>
            </div>
          </div>
        )}
      </div>
    </TooltipProvider>
  )
}
