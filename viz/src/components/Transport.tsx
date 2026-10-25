import { ChevronFirst, ChevronLast, Pause, Play, StepBack, StepForward } from 'lucide-react'
import type { Trace } from '@/contract/trace'
import { algorithmMeta } from '@/algorithms/registry'
import { prepare } from '@/engine/sample'
import { CALL_STATUS } from '@/engine/status'
import { SPEEDS, clock, clockActions, formatClock } from '@/playback/clock'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Slider } from '@/components/ui/slider'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

function Sparklines({ traces, span }: { traces: Trace[]; span: { start: number; end: number } }) {
  const W = 1000
  const H = 36
  const x = (t: number) => ((t - span.start) / (span.end - span.start)) * W
  const calls = traces[0]?.calls ?? []
  return (
    <svg aria-hidden="true" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="pointer-events-none absolute inset-x-0 bottom-3 h-9 w-full">
      {traces.map((tr) => {
        const p = prepare(tr)
        const max = Math.max(1, tr.vehicles.length)
        const pts = p.busySeries.map((b, i) => `${x(tr.span.start + i)},${H - 4 - (b / max) * (H - 10)}`).join(' ')
        const color = algorithmMeta(tr.algorithm.id).color
        return (
          <polyline key={tr.algorithm.id} points={`${x(tr.span.start)},${H - 4} ${pts} ${x(tr.span.end)},${H - 4}`}
            fill={color} fillOpacity={0.12} stroke={color} strokeOpacity={0.7} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
        )
      })}
      {calls.map((c) => (
        <rect key={c.id} x={x(c.time) - 0.75} y={H - 4} width={1.5} height={4} fill={CALL_STATUS.waiting.color} />
      ))}
    </svg>
  )
}

export function Transport({ traces }: { traces: Trace[] }) {
  const { time, playing, speed, span } = clock.use()
  const iconBtn = (label: string, onClick: () => void, icon: React.ReactNode, kbd: string) => (
    <Tooltip>
      <TooltipTrigger render={<Button variant="ghost" size="icon-sm" onClick={onClick} aria-label={label} />}>{icon}</TooltipTrigger>
      <TooltipContent>{label} <span className="ml-1 opacity-60">{kbd}</span></TooltipContent>
    </Tooltip>
  )

  return (
    <footer className="transport" aria-label="Playback controls">
      <div className="transport-buttons">
        {iconBtn('Jump to start', () => clockActions.seek(span.start), <ChevronFirst />, 'Home')}
        {iconBtn('Back 1 min', () => clockActions.step(-1), <StepBack />, '← (⇧ 10)')}
        <Button size="icon" className="play-button" onClick={clockActions.toggle} aria-label={playing ? 'Pause' : 'Play'}>
          {playing ? <Pause className="fill-current" /> : <Play className="fill-current" />}
        </Button>
        {iconBtn('Forward 1 min', () => clockActions.step(1), <StepForward />, '→ (⇧ 10)')}
        {iconBtn('Jump to end', () => clockActions.seek(span.end), <ChevronLast />, 'End')}
      </div>

      <div className="transport-clock"><span>{formatClock(time)}</span><span className="clock-caption">Simulation time</span></div>

      <div className="timeline-track">
        <Sparklines traces={traces} span={span} />
        <Slider className="relative z-10 -mt-7" min={span.start} max={span.end} step={0.25} value={time}
          onValueChange={(v) => clockActions.seek(Array.isArray(v) ? v[0] : v)} aria-label="Timeline" />
        <span className="absolute bottom-0 left-0 text-xs text-muted-foreground">{formatClock(span.start)}</span>
        <span className="absolute right-0 bottom-0 text-xs text-muted-foreground">{formatClock(span.end)}</span>
      </div>

      <Select value={String(speed)} onValueChange={(v) => v && clockActions.setSpeed(Number(v))}
        items={Object.fromEntries(SPEEDS.map((s) => [String(s), `${s} min/s`]))}>
        <SelectTrigger size="sm" className="w-28" aria-label="Playback speed">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {SPEEDS.map((s) => <SelectItem key={s} value={String(s)}>{s} min/s</SelectItem>)}
        </SelectContent>
      </Select>
    </footer>
  )
}
