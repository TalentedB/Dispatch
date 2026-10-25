import { useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Line } from '@react-three/drei'
import * as THREE from 'three'
import type { XY } from '@/contract/trace'

/** A rounded label for the 2D map. Sizes are in screen pixels (scaled by px). */
export function Pill({
  x, y, text, color, px, dy = 0, solid = false,
}: { x: number; y: number; text: string; color: string; px: number; dy?: number; solid?: boolean }) {
  const fs = 10.5 * px
  const w = (text.length * 6.1 + 12) * px
  const h = 16 * px
  return (
    <g transform={`translate(${x}, ${y + dy * px})`} style={{ pointerEvents: 'none' }}>
      <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={h / 2}
        fill={solid ? color : 'rgba(9, 9, 11, 0.85)'} stroke={color} strokeWidth={px} />
      <text textAnchor="middle" dominantBaseline="central" fontSize={fs} fontWeight={600}
        fill={solid ? '#09090b' : color} style={{ fontVariantNumeric: 'tabular-nums' }}>
        {text}
      </text>
    </g>
  )
}

export const toPoints = (path: XY[], sy: (y: number) => number) => path.map(([x, y]) => `${x},${sy(y)}`).join(' ')

/** Grid (x, y) + height -> three.js world coordinates (north is -z). */
export const world = (x: number, y: number, h: number): [number, number, number] => [x, h, -y]

export function Line3D({ path, height, color, width = 2, dashed = false, opacity = 1 }: {
  path: XY[]; height: (x: number, y: number) => number; color: string; width?: number; dashed?: boolean; opacity?: number
}) {
  if (path.length < 2) return null
  // Sample each leg so the line hugs the terrain instead of cutting through hills.
  const pts: [number, number, number][] = []
  for (let i = 1; i < path.length; i++) {
    const [a, b] = [path[i - 1], path[i]]
    const steps = Math.max(1, Math.ceil(Math.abs(b[0] - a[0]) + Math.abs(b[1] - a[1])))
    for (let s = i === 1 ? 0 : 1; s <= steps; s++) {
      const x = a[0] + ((b[0] - a[0]) * s) / steps
      const y = a[1] + ((b[1] - a[1]) * s) / steps
      pts.push(world(x, y, height(x, y) + 0.35))
    }
  }
  return (
    <Line points={pts} color={color} lineWidth={width} dashed={dashed} dashSize={0.6} gapSize={0.4}
      transparent opacity={opacity} />
  )
}

const textures = new Map<string, { tex: THREE.CanvasTexture; w: number; h: number }>()

/** A pill label drawn to a cached canvas texture (scaled 2x for crisp text). */
function labelTexture(text: string, color: string) {
  const key = `${color}|${text}`
  const hit = textures.get(key)
  if (hit) return hit
  const c = document.createElement('canvas')
  const g = c.getContext('2d')!
  const font = '600 21px Geist Variable, ui-sans-serif, system-ui, sans-serif'
  g.font = font
  const w = Math.ceil(g.measureText(text).width) + 26
  const h = 34
  c.width = w
  c.height = h
  g.font = font
  g.fillStyle = 'rgba(9, 9, 11, 0.88)'
  g.strokeStyle = color
  g.lineWidth = 2
  g.beginPath()
  g.roundRect(1, 1, w - 2, h - 2, h / 2)
  g.fill()
  g.stroke()
  g.fillStyle = color
  g.textBaseline = 'middle'
  g.textAlign = 'center'
  g.fillText(text, w / 2, h / 2 + 1)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  const entry = { tex, w: w / 2, h: h / 2 }
  textures.set(key, entry)
  if (textures.size > 400) {
    const [oldKey, old] = textures.entries().next().value!
    textures.delete(oldKey)
    old.tex.dispose()
  }
  return entry
}

/** Screen-space label anchored to a world point, `dy` pixels above it. Constant size at any zoom. */
export function Label3D({ at, text, color, dy = 0 }: { at: [number, number, number]; text: string; color: string; dy?: number }) {
  const { tex, w, h } = labelTexture(text, color)
  const ref = useRef<THREE.Sprite>(null)
  useFrame(({ camera }) => {
    const s = 1 / camera.zoom
    ref.current?.scale.set(w * s, h * s, 1)
  })
  return (
    <sprite ref={ref} position={at} center={new THREE.Vector2(0.5, 0.5 - dy / h)} renderOrder={10}>
      <spriteMaterial map={tex} depthTest={false} depthWrite={false} transparent />
    </sprite>
  )
}
