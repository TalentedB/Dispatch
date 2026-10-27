import { themeColor } from '@/lib/theme'
import { useLayoutEffect, useMemo, useRef } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { Box } from 'lucide-react'
import { nearestResponseTime, type CallFrame, type Bounds, type VehicleFrame } from '@/engine/sample'
import { CALL_STATUS, VEHICLE_STATUS } from '@/engine/status'
import { Line3D } from '@/overlays/shared'
import { OVERLAYS } from '@/overlays/registry'
import type { Map3DContext } from '@/overlays/types'
import { distanceColor } from './colors'
import type { ViewPlugin, ViewProps } from './types'
import { animateCamera } from './cameraMotion'

type Field = 'all' | 'free' | 'flat'

/** Height is response minutes: remaining locked work plus travel from the ready location. */
function useField(bounds: Bounds, vehicles: VehicleFrame[], field: Field) {
  const { minX, maxX, minY, maxY } = bounds
  const range = Math.max(8, (maxX - minX + maxY - minY) / 2)
  const k = 9 / range
  const sources = vehicles.filter((vehicle) => field === 'all'
    || vehicle.status === 'idle' || vehicle.status === 'to_base' || vehicle.status === 'reposition')
  const distAt = (x: number, y: number) => Math.min(range, nearestResponseTime(x, y, sources))
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

function Terrain({ bounds, distAt, heightAt, range }: {
  bounds: Bounds; distAt: (x: number, y: number) => number; heightAt: (x: number, y: number) => number; range: number
}) {
  const { minX, maxX, minY, maxY } = bounds
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

/** Minutes a resolved call's marker stays on the map, fading out (same as the top-down view). */
const DONE_FADE = 45

function CallPillar({ c, heightAt, k, vehicles, t, finish }: {
  c: CallFrame; heightAt: (x: number, y: number) => number; k: number; vehicles: VehicleFrame[]; t: number; finish?: number
}) {
  const mat = useRef<THREE.MeshStandardMaterial>(null)
  const color = CALL_STATUS[c.status].color
  useFrame(() => {
    if (mat.current) mat.current.emissiveIntensity = 0.3
  })
  const base = heightAt(c.call.x, c.call.y)
  if (c.status === 'done') {
    const age = finish === undefined ? DONE_FADE : t - finish
    if (age >= DONE_FADE) return null
    return (
      <mesh position={[c.call.x, base + 0.05, -c.call.y]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.35, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.6 * (1 - age / DONE_FADE)} />
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
  const y = heightAt(v.x, v.y)
  // Colour shows what the vehicle is doing, matching the top-down view.
  const color = VEHICLE_STATUS[v.status].color
  return (
    <group position={[v.x, y + 0.3, -v.y]}>
      <mesh>
        <boxGeometry args={[0.9, 0.5, 0.9]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.25} />
      </mesh>
      <mesh position={[0, 0.35, 0]}>
        <boxGeometry args={[0.4, 0.2, 0.25]} />
        <meshStandardMaterial color={themeColor('map-mark')} />
      </mesh>
    </group>
  )
}

function FitCamera({ bounds, exporting }: { bounds: Bounds; exporting?: boolean }) {
  const { get, size, gl } = useThree()
  const hasFitted = useRef(false)
  const { minX, maxX, minY, maxY } = bounds
  useLayoutEffect(() => {
    const camera = get().camera
    const span = Math.max(maxX - minX, maxY - minY)
    const cx = (minX + maxX) / 2
    const cz = -(minY + maxY) / 2
    const target = [cx + span, span * 0.95, cz + span, Math.min(size.width, size.height) / (Math.max(1, span) * 1.55)]
    const update = ([x, y, z, zoom]: number[]) => {
      camera.position.set(x, y, z)
      camera.lookAt(cx, 2, cz)
      camera.zoom = zoom
      camera.updateProjectionMatrix()
    }
    let cancel = () => {}
    if (!hasFitted.current) {
      hasFitted.current = true
      update(target)
    } else {
      cancel = animateCamera([...camera.position.toArray(), camera.zoom], target, update,
        exporting || window.matchMedia('(prefers-reduced-motion: reduce)').matches)
    }
    // User input takes ownership before OrbitControls handles the same event.
    gl.domElement.addEventListener('pointerdown', cancel, true)
    gl.domElement.addEventListener('wheel', cancel, true)
    return () => {
      cancel()
      gl.domElement.removeEventListener('pointerdown', cancel, true)
      gl.domElement.removeEventListener('wheel', cancel, true)
    }
  }, [minX, maxX, minY, maxY, get, gl, size.width, size.height, exporting])
  return null
}

// Render on capture even when the browser has suspended its animation loop.
function CaptureFrame() {
  const { gl, scene, camera } = useThree()
  useLayoutEffect(() => {
    const render = (event: Event) => {
      if ((event as CustomEvent<HTMLElement>).detail?.contains(gl.domElement)) gl.render(scene, camera)
    }
    window.addEventListener('dispatch:capture-frame', render)
    return () => window.removeEventListener('dispatch:capture-frame', render)
  }, [gl, scene, camera])
  return null
}

function Isometric({ prepared, frame, overlays, options, exporting }: ViewProps) {
  const bounds = frame.bounds
  const field = (options.surface ?? 'all') as Field
  const { distAt, heightAt, range, k } = useField(frame.bounds, frame.vehicles, field)
  const { minX, maxX, minY, maxY } = bounds
  const ctx: Map3DContext = { prepared, frame, heightAt }
  const active = OVERLAYS.filter((o) => overlays.has(o.id) && o.render.map3d)

  return (
    <div className="absolute inset-0">
      <Canvas orthographic gl={{ preserveDrawingBuffer: true }} dpr={[1, 2]} camera={{ near: -1000, far: 1000, position: [50, 50, 50] }}>
        <CaptureFrame />
        <color attach="background" args={[themeColor('map-paper')]} />
        <fog attach="fog" args={[themeColor('map-paper'), 200, 400]} />
        <FitCamera bounds={bounds} exporting={exporting} />
        <ambientLight intensity={0.55} />
        <hemisphereLight args={[themeColor('map-light'), themeColor('map-grid'), 0.5]} />
        <directionalLight position={[30, 60, 20]} intensity={1.6} />
        <Terrain bounds={bounds} distAt={distAt} heightAt={heightAt} range={range} />
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
        {/* The two streets through base, as solid graph axes like the top-down view. */}
        <Line3D path={[[minX, 0], [maxX, 0]]} height={heightAt} color={themeColor('map-axis')} width={3} />
        <Line3D path={[[0, minY], [0, maxY]]} height={heightAt} color={themeColor('map-axis')} width={3} />
        {frame.calls.filter((c) => c.status !== 'future').map((c) => (
          <CallPillar key={c.call.id} c={c} heightAt={heightAt} k={k} vehicles={frame.vehicles}
            t={frame.t} finish={prepared.callById.get(c.call.id)?.finish} />
        ))}
        {frame.vehicles.map((v) => <Vehicle key={v.id} v={v} heightAt={heightAt} />)}
        {active.map((o) => <group key={o.id}>{o.render.map3d!(ctx)}</group>)}
        <OrbitControls makeDefault target={[(minX + maxX) / 2, 2, -(minY + maxY) / 2]} enableDamping maxPolarAngle={Math.PI / 2.1} />
      </Canvas>
      <div className="pointer-events-none absolute bottom-2 left-2 flex items-center gap-2 text-xs text-muted-foreground">
        <span aria-label="Known city size">{maxX - minX} × {maxY - minY} blocks</span>
        {field !== 'flat' && (
          <span className="flex items-center gap-1.5" title={`Terrain height and colour: response time including remaining locked work${field === 'free' ? ' (free vehicles only)' : ''}`}>
            near <span className="h-1.5 w-16 rounded-full" style={{ background: 'var(--coverage-ramp)' }} /> far
          </span>
        )}
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
        { value: 'all', label: 'Response time including busy vehicles' },
        { value: 'free', label: 'Response time, free vehicles only' },
        { value: 'flat', label: 'Flat' },
      ],
    },
  ],
  component: Isometric,
}
