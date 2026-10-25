/** Resolve CSS tokens for canvas and WebGL, which cannot consume var(). */
export function themeColor(role: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--color-${role}`).trim()
}
