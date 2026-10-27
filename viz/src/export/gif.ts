import { GIFEncoder, quantize, applyPalette } from 'gifenc'
import { getFontEmbedCSS, toCanvas } from 'html-to-image'
import { captureRun } from './captureRun'
import { createCaptureView, type ExportPane } from './captureView'
import { planFrames } from './timing'

// Allow React effects, canvas drawing, and the WebGL render loop to finish.
const painted = (signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  let raf = 0
  const finish = () => {
    clearTimeout(timer)
    cancelAnimationFrame(raf)
    signal.removeEventListener('abort', abort)
    if (signal.aborted) reject(signal.reason)
    else resolve()
  }
  const abort = () => finish()
  // Browsers can suspend animation frames in an inactive tab. Effects still run.
  const timer = setTimeout(finish, 100)
  raf = requestAnimationFrame(() => { raf = requestAnimationFrame(finish) })
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) finish()
})

/** Render the complete run offscreen using the real panes and an independent time. */
export async function exportGif(source: HTMLElement, panes: ExportPane[], speed: number,
  signal: AbortSignal, progress: (percent: number) => void): Promise<Blob> {
  if (!panes.length) throw new Error('No run is loaded')
  const span = { start: Math.min(...panes.map((p) => p.trace.span.start)), end: Math.max(...panes.map((p) => p.trace.span.end)) }
  const frames = planFrames(span, speed, panes.map((p) => p.trace))
  await document.fonts.ready
  signal.throwIfAborted()
  const view = createCaptureView(source, panes)
  const gif = GIFEncoder()
  try {
    view.render(span.start)
    await painted(signal)
    const element = view.element
    const { width, height } = element.getBoundingClientRect()
    const ratio = Math.min(1, 1280 / width, 900 / height)
    const canvasWidth = Math.round(width * ratio)
    const canvasHeight = Math.round(height * ratio)
    const fontEmbedCSS = await getFontEmbedCSS(element, { preferredFontFormat: 'woff2' })
    await captureRun(frames, async ({ time, delay }) => {
        view.render(time)
        // Yield for the separate React Three Fiber root and canvas effects, not simulation time.
        await new Promise((resolve) => setTimeout(resolve, 0))
        signal.throwIfAborted()
        window.dispatchEvent(new CustomEvent('dispatch:capture-frame', { detail: element }))
        const canvas = await toCanvas(element, {
          pixelRatio: 1, canvasWidth, canvasHeight, fontEmbedCSS,
          backgroundColor: getComputedStyle(document.documentElement).getPropertyValue('--color-cotton').trim(),
        })
        signal.throwIfAborted()
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        if (!ctx) throw new Error('Canvas is unavailable')
        const data = ctx.getImageData(0, 0, canvasWidth, canvasHeight).data
        const palette = quantize(data, 256)
        gif.writeFrame(applyPalette(data, palette), canvasWidth, canvasHeight, {
          palette, delay, repeat: 0,
        })
    }, signal, progress)
  } finally {
    view.dispose()
  }
  gif.finish()
  return new Blob([gif.bytes()], { type: 'image/gif' })
}
