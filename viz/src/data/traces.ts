import { useEffect, useState } from 'react'
import { validateTrace, type Manifest, type ManifestScenario, type Trace } from '@/contract/trace'
import { createStore } from '@/lib/store'
import { registerAlgorithm } from '@/algorithms/registry'

/**
 * Where traces come from: the exported manifest (public/traces, written by
 * tools/export_viz.py) plus any trace files the user drops onto the app.
 */

interface DataState {
  manifest: Manifest | null
  error: string | null
  uploaded: Record<string, Record<string, Trace>> // scenario -> algorithm -> trace
}

export const dataStore = createStore<DataState>({ manifest: null, error: null, uploaded: {} })

const BASE = `${import.meta.env.BASE_URL}traces/`
const fetched = new Map<string, Promise<Trace>>()

export async function loadManifest() {
  try {
    const res = await fetch(`${BASE}manifest.json`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    dataStore.set({ manifest: await res.json() })
  } catch (e) {
    dataStore.set({
      error: `Couldn't load traces/manifest.json (${(e as Error).message}). Run: python3 tools/export_viz.py`,
      manifest: { schema: '', algorithms: [], scenarios: [] },
    })
  }
}

export interface ScenarioEntry extends Omit<ManifestScenario, 'traces'> {
  algorithms: string[]
}

export function useScenarios(): ScenarioEntry[] {
  const { manifest, uploaded } = dataStore.use()
  const byId = new Map<string, ScenarioEntry>()
  for (const s of manifest?.scenarios ?? []) byId.set(s.id, { ...s, algorithms: Object.keys(s.traces) })
  for (const [id, algos] of Object.entries(uploaded)) {
    const first = Object.values(algos)[0]
    const entry = byId.get(id) ?? {
      id,
      label: first.scenario.label ?? id,
      group: 'uploaded',
      vehicles: first.scenario.vehicles,
      calls: first.calls.length,
      algorithms: [],
    }
    entry.algorithms = [...new Set([...entry.algorithms, ...Object.keys(algos)])]
    byId.set(id, entry)
  }
  return [...byId.values()]
}

export function getTrace(scenario: string, algorithm: string): Promise<Trace> {
  const local = dataStore.get().uploaded[scenario]?.[algorithm]
  if (local) return Promise.resolve(local)
  const rel = dataStore.get().manifest?.scenarios.find((s) => s.id === scenario)?.traces[algorithm]
  if (!rel) return Promise.reject(new Error(`No trace for ${algorithm} on ${scenario}`))
  let p = fetched.get(rel)
  if (!p) {
    p = fetch(BASE + rel)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(validateTrace)
    fetched.set(rel, p)
  }
  return p
}

export function useTrace(scenario: string | null, algorithm: string | null) {
  const [state, setState] = useState<{ key: string; trace: Trace | null; error: string | null }>({
    key: '',
    trace: null,
    error: null,
  })
  const key = `${scenario}/${algorithm}`
  const uploaded = dataStore.use((s) => s.uploaded)
  useEffect(() => {
    if (!scenario || !algorithm) return
    let live = true
    getTrace(scenario, algorithm).then(
      (trace) => live && setState({ key, trace, error: null }),
      (e: Error) => live && setState({ key, trace: null, error: e.message }),
    )
    return () => {
      live = false
    }
  }, [scenario, algorithm, key, uploaded])
  return state.key === key ? state : { key, trace: null, error: null }
}

/** Every trace for a scenario, for the comparison table. */
export function useScenarioTraces(scenario: ScenarioEntry | undefined) {
  const [traces, setTraces] = useState<Trace[]>([])
  const id = scenario?.id
  const algos = scenario?.algorithms.join(',')
  useEffect(() => {
    if (!id || !algos) return
    let live = true
    Promise.allSettled(algos.split(',').map((a) => getTrace(id, a))).then((rs) => {
      if (live) setTraces(rs.flatMap((r) => (r.status === 'fulfilled' ? [r.value] : [])))
    })
    return () => {
      live = false
    }
  }, [id, algos])
  return traces.filter((t) => t.scenario.id === id)
}

export async function addTraceFiles(files: FileList | File[]): Promise<{ added: Trace[]; errors: string[] }> {
  const added: Trace[] = []
  const errors: string[] = []
  for (const f of Array.from(files)) {
    try {
      const data = JSON.parse(await f.text())
      for (const item of Array.isArray(data) ? data : [data]) added.push(validateTrace(item))
    } catch (e) {
      errors.push(`${f.name}: ${(e as Error).message}`)
    }
  }
  if (added.length) {
    dataStore.set((s) => {
      const uploaded = { ...s.uploaded }
      for (const t of added) {
        registerAlgorithm(t.algorithm.id, t.algorithm)
        uploaded[t.scenario.id] = { ...uploaded[t.scenario.id], [t.algorithm.id]: t }
      }
      return { uploaded }
    })
  }
  return { added, errors }
}
