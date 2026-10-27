import { createRoot } from 'react-dom/client'
import { flushSync } from 'react-dom'
import { Pane, type PaneState } from '@/components/Pane'
import { TooltipProvider } from '@/components/ui/tooltip'
import type { Trace } from '@/contract/trace'

export interface ExportPane { state: PaneState; trace: Trace; algorithms: string[] }

/** The same React panes, mounted outside the viewport with a private time prop. */
export function createCaptureView(source: HTMLElement, panes: ExportPane[]) {
  const { width, height } = source.getBoundingClientRect()
  if (width < 1 || height < 1) throw new Error('The simulation view is not visible')
  const host = document.createElement('div')
  host.className = 'dispatch-app'
  host.setAttribute('aria-hidden', 'true')
  host.inert = true
  Object.assign(host.style, {
    position: 'fixed', left: '-100000px', top: '0', width: `${width}px`, height: `${height}px`,
    minHeight: '0', maxWidth: 'none', margin: '0', border: '0', pointerEvents: 'none',
  })
  document.body.append(host)
  const root = createRoot(host)
  const render = (time: number) => flushSync(() => root.render(
    <TooltipProvider>
      <main className={`workspace ${panes.length > 1 ? 'is-split' : ''}`}>
        <div className="simulation-panes" style={{ width, height, flex: 'none' }}>
          {panes.map((pane, i) => <Pane key={i} {...pane} onChange={() => {}} error={null} time={time} />)}
        </div>
      </main>
    </TooltipProvider>,
  ))
  return {
    render,
    get element() { return host.querySelector<HTMLElement>('.simulation-panes')! },
    dispose: () => { root.unmount(); host.remove() },
  }
}
