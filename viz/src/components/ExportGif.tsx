import { useEffect, useRef, useState } from 'react'
import type { ExportPane } from '@/export/captureView'
import { Button } from '@/components/ui/button'
import { clock } from '@/playback/clock'

export function ExportGif({ panes, ready }: { panes: ExportPane[]; ready: boolean }) {
  const speed = clock.use((s) => s.speed)
  const span = panes.length ? Math.max(...panes.map((p) => p.trace.span.end)) - Math.min(...panes.map((p) => p.trace.span.start)) : 0
  const [progress, setProgress] = useState<number | null>(null)
  const [error, setError] = useState('')
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  const run = async () => {
    if (!panes.length || !ready || controller.current) return
    const element = document.querySelector<HTMLElement>('.simulation-panes')
    if (!element) return
    const selected = panes.map((pane) => ({ ...pane, state: { ...pane.state, overlays: new Set(pane.state.overlays) } }))
    const selectedSpeed = speed
    const trace = selected[0].trace
    const abort = new AbortController()
    controller.current = abort
    setProgress(0)
    setError('')
    try {
      const { exportGif } = await import('@/export/gif')
      const blob = await exportGif(element, selected, selectedSpeed, abort.signal, setProgress)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${trace.scenario.id}-${trace.algorithm.id}.gif`.replace(/[^a-zA-Z0-9._-]/g, '_')
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 10000)
    } catch (e) {
      if (!abort.signal.aborted) setError(e instanceof Error ? e.message : 'GIF export failed')
    } finally {
      controller.current = null
      setProgress(null)
    }
  }
  return <div>
    <div className="flex items-center gap-2 flex-wrap">
    <span className="text-xs">At playback speed: {speed} min/s · {(span / speed).toFixed(1)}s</span>
    <Button variant="outline" size="sm" disabled={!panes.length || !ready || progress !== null} onClick={() => void run()}>Export GIF</Button>
    <span className="inline-flex min-w-48 min-h-8 items-center gap-2">
      {progress !== null && <><span role="status" className="text-xs">Exporting {progress}%</span><Button variant="ghost" size="sm" onClick={() => controller.current?.abort()}>Cancel</Button></>}
    </span>
    </div>
    {error && <span role="alert" className="text-xs text-destructive">{error}</span>}
    <p className="text-xs text-muted-foreground">Full run, rendered offscreen · current views and layers · both panes in split view</p>
  </div>
}
