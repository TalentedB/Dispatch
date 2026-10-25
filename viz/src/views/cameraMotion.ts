/** Camera-only motion: simulation coordinates and report times remain exact. */
export const CAMERA_TRANSITION_MS = 420

export function animateCamera(
  from: number[],
  to: number[],
  update: (values: number[]) => void,
  reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches,
): () => void {
  if (reducedMotion) {
    update(to)
    return () => {}
  }
  let request = 0
  let cancelled = false
  const started = performance.now()
  const step = (now: number) => {
    if (cancelled) return
    const progress = Math.min(1, Math.max(0, (now - started) / CAMERA_TRANSITION_MS))
    const eased = 1 - (1 - progress) ** 3
    update(progress === 1 ? to : from.map((value, index) => value + (to[index] - value) * eased))
    if (progress < 1) request = requestAnimationFrame(step)
  }
  request = requestAnimationFrame(step)
  return () => {
    cancelled = true
    cancelAnimationFrame(request)
  }
}
