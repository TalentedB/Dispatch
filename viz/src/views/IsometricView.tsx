import { themeColor } from '@/lib/theme'
import { useLayoutEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { Box } from 'lucide-react'
import type { XY } from '@/contract/trace'
import { nearestDistance, type CallFrame, type Prepared, type VehicleFrame } from '@/engine/sample'
import { CALL_STATUS, vehicleColor } from '@/engine/status'
import { OVERLAYS } from '@/overlays/registry'
import type { Map3DContext } from '@/overlays/types'
import { distanceColor } from './colors'
import type { ViewPlugin, ViewProps } from './types'

type Field = 'all' | 'free' | 'flat'

/** Height function for the terrain: drive time from each point to the nearest (free) vehicle. */
function useField(prepared: Prepared, vehicles: VehicleFrame[], field: Field) {
  const { minX, maxX, minY, maxY } = prepared.bounds
  const range = Math.max(8, (maxX - minX + maxY - minY) / 2)
  const k = 9 / range
  const sources: XY[] = vehicles
    .filter((v) => field === 'all' || v.status === 'idle' || v.status === 'to_base')
    .map((v) => [v.x, v.y])
  const distAt = (x: number, y: number) => (sources.length ? Math.min(range, nearestDistance(x, y, sources)) : range)
  const heightAt = (x: number, y: number) => (field === 'flat' ? 0 : distAt(x, y) * k)
  return { distAt, heightAt, range, k }
}

function gridTexture() {
  const c = document.createElement('canvas')
  c.width = c.height = 64
  const g = c.getContext('2d')!
  g.fillStyle = themeColor('map-mark')
  g.fillRect(0, 0, 64, 64)
  g.fillStyle = themeColor('map-axis')
  g.fillRect(0, 0, 64, 3)
  g.fillRect(0, 0, 3, 64)
  const t = new THREE.CanvasTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.anisotropy = 8
  return t
}

function Terrain({ prepared, distAt, heightAt, range }: {
  prepared: Prepared; distAt: (x: number, y: number) => number; heightAt: (x: number, y: number) => number; range: number
}) {
  const { minX, maxX, minY, maxY } = prepared.bounds
  const W = maxX - minX
  const H = maxY - minY
  const geom = useMemo(() => {
    const g = new THREE.PlaneGeometry(W, H, W, H)
    g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(g.attributes.position.count * 3), 3))
    // UVs in grid units so the grid texture repeats once per block.
    const uv = g.attributes.uv
    for (let k = 0; k < uv.count; k++) uv.setXY(k, uv.getX(k) * W, uv.getY(k) * H)
    return g
  }, [W, H])
  const tex = useMemo(gridTexture, [])

  useLayoutEffect(() => {
    const pos = geom.attributes.position
    const col = geom.attributes.color
    let k = 0
    for (let j = 0; j <= H; j++) {
      for (let i = 0; i <= W; i++, k++) {
        const x = minX + i
        const y = maxY - j
        pos.setXYZ(k, x, heightAt(x, y), -y)
        const [r, g, b] = distanceColor(distAt(x, y) / range)
        col.setXYZ(k, r / 255, g / 255, b / 255)
      }
    }
    pos.needsUpdate = true
    col.needsUpdate = true
    geom.computeVertexNormals()
    geom.computeBoundingSphere()
  })

  return (
    <mesh geometry={geom}>
      <meshStandardMaterial vertexColors map={tex} flatShading roughness={0.85} metalness={0.05} side={THREE.DoubleSide} />
    </mesh>
  )
}

function CallPillar({ c, heightAt, k, vehicles }: {
  c: CallFrame; heightAt: (x: number, y: number) => number; k: number; vehicles: VehicleFrame[]
}) {
  const mat = useRef<THREE.MeshStandardMaterial>(null)
  const color = CALL_STATUS[c.status].color
  useFrame(() => {
    if (mat.current) mat.current.emissiveIntensity = 0.3
  })
  const base = heightAt(c.call.x, c.call.y)
  if (c.status === 'done') {
    return (
      <mesh position={[c.call.x, base + 0.05, -c.call.y]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.35, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.6} />
      </mesh>
    )
  }
  // Pillar height = blocks between the emergency and its responding vehicle (or the nearest one, if waiting).
  const responder = vehicles.find((v) => v.call?.id === c.call.id)
  const dist = responder
    ? responder.blocksToTarget
    : Math.min(...vehicles.map((v) => Math.abs(v.x - c.call.x) + Math.abs(v.y - c.call.y)))
  const h = Math.max(0.4, dist * k * 0.8 + 0.4)
  return (
    <group position={[c.call.x, base, -c.call.y]}>
      <mesh position={[0, h / 2, 0]}>
        <cylinderGeometry args={[0.32, 0.42, h, 12]} />
        <meshStandardMaterial ref={mat} color={color} emissive={color} emissiveIntensity={0.5} transparent opacity={0.92} />
      </mesh>
      <mesh position={[0, h + 0.3, 0]}>
        <octahedronGeometry args={[0.38]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={1} />
      </mesh>
    </group>
  )
}

function Vehicle({ v, heightAt }: { v: VehicleFrame; heightAt: (x: number, y: number) => number }) {
  const light = useRef<THREE.MeshStandardMaterial>(null)
  useFrame(() => {
    if (!light.current) return
    const on = v.status === 'to_job'
    light.current.emissive.set(v.status === 'to_job' ? (on ? themeColor('state-scene') : themeColor('state-return')) : themeColor('state-idle'))
  })
  const y = heightAt(v.x, v.y)
  const color = vehicleColor(v.id)
  return (
    <group position={[v.x, y + 0.3, -v.y]}>
      <mesh>
        <boxGeometry args={[0.9, 0.5, 0.9]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.25} />
      </mesh>
      <mesh position={[0, 0.35, 0]}>
        <boxGeometry args={[0.4, 0.2, 0.25]} />
        <meshStandardMaterial ref={light} color={themeColor('map-grid')} emissiveIntensity={2} />
      </mesh>
    </group>
  )
}

function FitCamera({ prepared }: { prepared: Prepared }) {
  const { camera, size } = useThree()
  const { minX, maxX, minY, maxY } = prepared.bounds
  useLayoutEffect(() => {
    const span = Math.max(maxX - minX, maxY - minY)
    const cx = (minX + maxX) / 2
    const cz = -(minY + maxY) / 2
    camera.position.set(cx + span, span * 0.95, cz + span)
    camera.lookAt(cx, 2, cz)
    camera.zoom = Math.min(size.width, size.height) / (span * 1.55)
    camera.updateProjectionMatrix()
    // Only refit when the scenario changes, so user zoom/rotation survives playback.
  }, [minX, maxX, minY, maxY])
  return null
}

function Isometric({ prepared, frame, overlays, options }: ViewProps) {
  const field = (options.surface ?? 'all') as Field
  const { distAt, heightAt, range, k } = useField(prepared, frame.vehicles, field)
  const { minX, maxX, minY, maxY } = prepared.bounds
  const ctx: Map3DContext = { prepared, frame, heightAt }
  const active = OVERLAYS.filter((o) => overlays.has(o.id) && o.render.map3d)

  return (
    <div className="absolute inset-0">
      <Canvas orthographic dpr={[1, 2]} camera={{ near: -1000, far: 1000, position: [50, 50, 50] }}>
        <color attach="background" args={[themeColor('map-paper')]} />
        <fog attach="fog" args={[themeColor('map-paper'), 200, 400]} />
        <FitCamera prepared={prepared} />
        <ambientLight intensity={0.55} />
        <hemisphereLight args={[themeColor('map-light'), themeColor('map-grid'), 0.5]} />
        <directionalLight position={[30, 60, 20]} intensity={1.6} />
        <Terrain prepared={prepared} distAt={distAt} heightAt={heightAt} range={range} />
        <group position={[0, heightAt(0, 0), 0]}>
          <mesh position={[0, 0.6, 0]}>
            <boxGeometry args={[1.4, 1.2, 1.4]} />
            <meshStandardMaterial color={themeColor('map-base')} emissive={themeColor('map-base')} emissiveIntensity={0.6} />
          </mesh>
          <mesh position={[0, 1.25, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[0.9, 0.25]} />
            <meshBasicMaterial color={themeColor('map-mark')} />
          </mesh>
          <mesh position={[0, 1.251, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 2]}>
            <planeGeometry args={[0.9, 0.25]} />
            <meshBasicMaterial color={themeColor('map-mark')} />
          </mesh>
          <pointLight color={themeColor('state-return')} intensity={30} distance={12} position={[0, 2, 0]} />
        </group>
        {frame.calls.filter((c) => c.status !== 'future').map((c) => (
          <CallPillar key={c.call.id} c={c} heightAt={heightAt} k={k} vehicles={frame.vehicles} />
        ))}
        {frame.vehicles.map((v) => <Vehicle key={v.id} v={v} heightAt={heightAt} />)}
        {active.map((o) => <group key={o.id}>{o.render.map3d!(ctx)}</group>)}
        <OrbitControls makeDefault target={[(minX + maxX) / 2, 2, -(minY + maxY) / 2]} enableDamping maxPolarAngle={Math.PI / 2.1} />
      </Canvas>
      <div className="pointer-events-none absolute bottom-2 left-2 flex items-center gap-2 text-xs text-muted-foreground">
        <span>terrain height &amp; colour = drive time to nearest {field === 'free' ? 'free ' : ''}vehicle</span>
        <span className="h-1.5 w-20 rounded-full" style={{ background: 'var(--coverage-ramp)' }} />
        <span>Pillar: distance to responder. Drag to orbit.</span>
      </div>
    </div>
  )
}

export const isometricView: ViewPlugin = {
  id: 'isometric',
  label: 'Isometric 3D',
  icon: Box,
  slot: 'map3d',
  options: [
    {
      id: 'surface',
      label: 'Terrain',
      default: 'all',
      choices: [
        { value: 'all', label: 'Distance to nearest vehicle' },
        { value: 'free', label: 'Distance to nearest free vehicle' },
        { value: 'flat', label: 'Flat' },
      ],
    },
  ],
  component: Isometric,
}
