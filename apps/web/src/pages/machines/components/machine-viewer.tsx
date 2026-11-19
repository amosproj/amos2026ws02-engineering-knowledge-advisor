import {
    useEffect,
    useEffectEvent,
    useLayoutEffect,
    useMemo,
    useRef,
    useState,
    useSyncExternalStore,
} from 'react'
import { useQuery } from '@tanstack/react-query'
import { CameraControls, CameraControlsImpl, GizmoHelper, GizmoViewcube } from '@react-three/drei'
import { Canvas, useThree, type ThreeEvent } from '@react-three/fiber'
import {
    Box3,
    Color,
    Mesh,
    PerspectiveCamera,
    PMREMGenerator,
    Sphere,
    Texture,
    Vector3,
    type Material,
    type Object3D,
} from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'

import { Home09Icon, Settings05Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Button,
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    Spinner,
    useSettings,
} from '@components'
import { ViewerSettings } from '@pages/settings/components/viewer-settings'

import { errorCode } from '../models/machine-errors'
import {
    MOUSE_PROFILES,
    activeModifier,
    buttonActions,
    type Modifier,
    type MouseAction,
} from '../models/mouse-profile-model'
import { fitDistance, visibleCenterShift, type ViewInset } from '../models/viewer-camera-model'
import { fetchModel } from '../query/machine-api'
import {
    buildSketch,
    disposeSketch,
    setSketchColor,
    showSketch,
    type Sketch,
} from './machine-sketch'
import type { NavigationSpeed } from '@pages/settings/models/settings-model'

const { ACTION } = CameraControlsImpl
const ACTIONS: Record<MouseAction, 0 | 1 | 2 | 16> = {
    rotate: ACTION.ROTATE,
    pan: ACTION.TRUCK,
    zoom: ACTION.DOLLY,
    none: ACTION.NONE,
}
const ISOMETRIC = new Vector3(1, 0.8, 1).normalize()
const FOV = 45
const SPEED_FACTORS: Record<NavigationSpeed, number> = { slow: 0.5, normal: 1, fast: 2 }

const HIGHLIGHT = new Color('#2563eb')
const SKETCH_COLORS = { light: '#8f8f8f', dark: '#6e6e6e' }
// Pointer travel in pixels beyond which a press is a camera drag, not a click
const CLICK_TOLERANCE = 4

const loader = new GLTFLoader()

/** Parts the page asks to show, as occurrence ids. */
export type ViewState = {
    selected: string[]
    hidden: string[]
    isolated: string[] | undefined
}

/** ``sequence`` repeats a request for the same parts. */
export type FrameRequest = { targets: string[]; sequence: number }

type Model = {
    scene: Object3D
    sphere: Sphere | null
    parts: Map<string, Object3D>
    /** In scene traversal order: the meshes of a part follow each other. */
    meshes: Mesh[]
    meshIndex: Map<Mesh, number>
    originals: (Material | Material[])[]
    ranges: Map<string, [number, number]>
    highlights: Map<Material, Material>
}

async function loadModel(fileId: string, signal: AbortSignal): Promise<Model> {
    const gltf = await loader.parseAsync(await fetchModel(fileId, signal), '')
    const parts = new Map<string, Object3D>()
    const meshes: Mesh[] = []
    const ranges = new Map<string, [number, number]>()
    const walk = (object: Object3D) => {
        const start = meshes.length
        if (object instanceof Mesh) meshes.push(object)
        for (const child of object.children) walk(child)
        const id: unknown = object.userData.occurrenceId
        if (typeof id === 'string') {
            parts.set(id, object)
            ranges.set(id, [start, meshes.length])
        }
    }
    walk(gltf.scene)
    const model: Model = {
        scene: gltf.scene,
        sphere: null,
        parts,
        meshes,
        meshIndex: new Map(meshes.map((mesh, i) => [mesh, i])),
        originals: meshes.map((mesh) => mesh.material),
        ranges,
        highlights: new Map(),
    }
    if (signal.aborted) {
        disposeModel(model)
        throw signal.reason
    }
    const box = new Box3().setFromObject(gltf.scene)
    if (box.isEmpty()) return model
    const sphere = box.getBoundingSphere(new Sphere())
    sphere.radius = Math.max(sphere.radius, 1e-3)
    return { ...model, sphere }
}

function disposeModel({ meshes, originals, highlights }: Model) {
    meshes.forEach((mesh, i) => {
        mesh.geometry.dispose()
        for (const original of [originals[i]].flat()) {
            for (const value of Object.values(original)) {
                if (value instanceof Texture) value.dispose()
            }
            original.dispose()
        }
    })
    // Highlights share the textures of their original
    for (const material of highlights.values()) material.dispose()
}

function highlightOf({ highlights }: Model, material: Material) {
    let highlight = highlights.get(material)
    if (!highlight) {
        highlight = material.clone()
        if ('color' in highlight && highlight.color instanceof Color) {
            highlight.color.lerp(HIGHLIGHT, 0.7)
        }
        if ('emissive' in highlight && highlight.emissive instanceof Color) {
            highlight.emissive.copy(HIGHLIGHT).multiplyScalar(0.3)
        }
        highlights.set(material, highlight)
    }
    return highlight
}

function fillRanges(model: Model, mask: Uint8Array, ids: string[], value: number) {
    for (const id of ids) {
        const range = model.ranges.get(id)
        if (range) mask.fill(value, ...range)
    }
}

function shownMeshes(model: Model, hidden: string[], isolated: string[] | undefined) {
    const shown = new Uint8Array(model.meshes.length).fill(isolated ? 0 : 1)
    if (isolated) fillRanges(model, shown, isolated, 1)
    fillRanges(model, shown, hidden, 0)
    return shown
}

function showView(model: Model, shown: Uint8Array, selectedIds: string[], sketch?: Sketch) {
    const selected = new Uint8Array(model.meshes.length)
    fillRanges(model, selected, selectedIds, 1)
    // A hidden selection leaves the shown meshes solid instead of turning them all to edges
    const sketching = sketch !== undefined && selected.some((flag, i) => flag && shown[i])
    const drawn = new Uint8Array(model.meshes.length)
    model.meshes.forEach((mesh, i) => {
        const original = model.originals[i]
        const highlighted = shown[i] && selected[i]
        // Meshes hidden for the sketch still catch clicks: the raycaster ignores visibility
        mesh.visible = Boolean(shown[i] && (!sketching || selected[i]))
        mesh.material =
            sketching || !highlighted
                ? original
                : Array.isArray(original)
                  ? original.map((material) => highlightOf(model, material))
                  : highlightOf(model, original)
        drawn[i] = sketching && shown[i] && !selected[i] ? 1 : 0
    })
    if (sketch) showSketch(sketch, drawn)
}

function subscribeToTheme(onChange: () => void) {
    const observer = new MutationObserver(onChange)
    observer.observe(document.documentElement, { attributeFilter: ['class'] })
    return () => observer.disconnect()
}

const isDarkTheme = () => document.documentElement.classList.contains('dark')

function occurrencePath(object: Object3D | null) {
    const ids: string[] = []
    for (; object; object = object.parent) {
        const id: unknown = object.userData.occurrenceId
        if (typeof id === 'string') ids.push(id)
    }
    return ids
}

type MachineViewerProps = {
    fileId: string
    inset: ViewInset
    view: ViewState
    frameRequest: FrameRequest | undefined
    onPick: (occurrenceIds: string[]) => void
    onMiss: () => void
}

export default function MachineViewer({
    fileId,
    inset,
    view,
    frameRequest,
    onPick,
    onMiss,
}: MachineViewerProps) {
    const model = useQuery({
        queryKey: ['models', fileId],
        queryFn: ({ signal }) => loadModel(fileId, signal),
        staleTime: Infinity,
        gcTime: 0,
    })
    const [resetCount, setResetCount] = useState(0)
    const [settingsOpen, setSettingsOpen] = useState(false)
    const dragged = useRef(false)
    const data = model.data
    const { settings } = useSettings()
    const sketching = settings.selectionStyle === 'sketch'
    const [built, setBuilt] = useState<{ model: Model; sketch: Sketch }>()
    // Releases the edges of a replaced model, the dispose effect below runs on the change
    if (built && built.model !== data) setBuilt(undefined)
    const sketch = sketching && built?.model === data ? built?.sketch : undefined

    useEffect(() => {
        if (!data) return
        return () => disposeModel(data)
    }, [data])

    useEffect(() => {
        if (!data?.sphere || !sketching || built?.model === data) return
        const controller = new AbortController()
        buildSketch(data.scene, data.meshes, controller.signal)
            .then((result) => setBuilt({ model: data, sketch: result }))
            // Without edges the selection stays opaque
            .catch(() => undefined)
        return () => controller.abort()
    }, [data, sketching, built])

    useEffect(() => {
        if (!built) return
        return () => disposeSketch(built.sketch)
    }, [built])

    if (model.isPending) {
        return (
            <Overlay inset={inset}>
                <Spinner />
            </Overlay>
        )
    }
    if (model.isError) {
        return errorCode(model.error) === 'model_unavailable' ? (
            <Overlay inset={inset}>No 3D model for this CAD file.</Overlay>
        ) : (
            <Overlay inset={inset}>
                <p>The 3D model could not be loaded.</p>
                <Button variant="outline" size="sm" onClick={() => void model.refetch()}>
                    Try again
                </Button>
            </Overlay>
        )
    }
    const { sphere } = model.data
    if (!sphere) {
        return <Overlay inset={inset}>The 3D model is empty.</Overlay>
    }

    return (
        <>
            <Canvas
                flat
                frameloop="demand"
                dpr={[1, 2]}
                camera={{ fov: FOV }}
                onPointerMissed={(event) => {
                    if (event.type === 'click' && !dragged.current) onMiss()
                }}
            >
                <Lighting />
                <Scene
                    model={model.data}
                    sphere={sphere}
                    inset={inset}
                    resetCount={resetCount}
                    view={view}
                    frameRequest={frameRequest}
                    sketch={sketch}
                    dragged={dragged}
                    onPick={onPick}
                    onMiss={onMiss}
                />
            </Canvas>
            <Button
                variant="ghost"
                size="icon"
                aria-label="Viewer settings"
                title="Viewer settings"
                className="text-muted-foreground absolute"
                style={{ right: 15, bottom: 150 }}
                onClick={() => setSettingsOpen(true)}
            >
                <HugeiconsIcon icon={Settings05Icon} strokeWidth={1.5} className="size-5" />
            </Button>
            <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
                <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg md:max-w-4xl">
                    <DialogHeader>
                        <DialogTitle>3D viewer settings</DialogTitle>
                    </DialogHeader>
                    <ViewerSettings columns />
                </DialogContent>
            </Dialog>
            <Button
                variant="ghost"
                size="icon"
                aria-label="Reset view"
                title="Reset view"
                className="text-muted-foreground absolute"
                style={{ right: 15, bottom: 110 }}
                onClick={() => setResetCount((count) => count + 1)}
            >
                <HugeiconsIcon icon={Home09Icon} strokeWidth={1.5} className="size-5" />
            </Button>
        </>
    )
}

function Overlay({ inset, children }: { inset: ViewInset; children: React.ReactNode }) {
    return (
        <div
            className="text-muted-foreground absolute inset-y-0 flex flex-col items-center justify-center gap-2 text-sm"
            style={{ left: inset.left, right: inset.right }}
        >
            {children}
        </div>
    )
}

function Lighting() {
    const get = useThree((state) => state.get)

    useEffect(() => {
        const { gl, scene } = get()
        const pmrem = new PMREMGenerator(gl)
        const room = new RoomEnvironment()
        const environment = pmrem.fromScene(room, 0.04)
        scene.environment = environment.texture
        scene.environmentIntensity = 0.7
        room.dispose()
        pmrem.dispose()
        return () => {
            scene.environment = null
            environment.dispose()
        }
    }, [get])

    return <directionalLight position={[1, 2, 1.5]} intensity={0.8} />
}

type SceneProps = {
    model: Model
    sphere: Sphere
    inset: ViewInset
    resetCount: number
    view: ViewState
    frameRequest: FrameRequest | undefined
    sketch: Sketch | undefined
    dragged: React.RefObject<boolean>
    onPick: (occurrenceIds: string[]) => void
    onMiss: () => void
}

function Scene({
    model,
    sphere,
    inset,
    resetCount,
    view,
    frameRequest,
    sketch,
    dragged,
    onPick,
    onMiss,
}: SceneProps) {
    const { settings } = useSettings()
    const profile = MOUSE_PROFILES[settings.mouseProfile]
    const speed = SPEED_FACTORS[settings.navigationSpeed]
    const controls = useRef<CameraControlsImpl>(null)
    const get = useThree((state) => state.get)
    const size = useThree((state) => state.size)
    const invalidate = useThree((state) => state.invalidate)

    useLayoutEffect(() => {
        const camera = get().camera as PerspectiveCamera
        const shift = visibleCenterShift(inset)
        camera.setViewOffset(size.width, size.height, -shift, 0, size.width, size.height)
        controls.current?.setViewport(shift, 0, size.width, size.height)
        invalidate()
    }, [get, size, inset, invalidate])

    useEffect(() => {
        const cameraControls = controls.current
        if (!cameraControls) return
        const camera = get().camera as PerspectiveCamera
        // Small enough to frame a screw of a large machine
        cameraControls.minDistance = sphere.radius * 1e-4
        cameraControls.maxDistance = sphere.radius * 50
        // Follows the distance, a fixed near plane would clip small parts seen up close
        const fitClipping = () => {
            camera.near = cameraControls.distance * 0.01
            camera.far = camera.position.distanceTo(sphere.center) + sphere.radius * 2
            camera.updateProjectionMatrix()
        }
        fitClipping()
        cameraControls.addEventListener('update', fitClipping)
        return () => cameraControls.removeEventListener('update', fitClipping)
    }, [get, sphere])

    useEffect(() => {
        const element = get().gl.domElement
        const pointers = new Set<number>()
        let start = { x: 0, y: 0 }
        const onDown = (event: PointerEvent) => {
            pointers.add(event.pointerId)
            if (pointers.size > 1) {
                dragged.current = true
                return
            }
            start = { x: event.clientX, y: event.clientY }
            dragged.current = false
        }
        const onMove = (event: PointerEvent) => {
            if (!pointers.has(event.pointerId)) return
            const travel = Math.hypot(event.clientX - start.x, event.clientY - start.y)
            if (travel > CLICK_TOLERANCE) dragged.current = true
        }
        const onUp = (event: PointerEvent) => pointers.delete(event.pointerId)
        const onCancel = (event: PointerEvent) => {
            pointers.delete(event.pointerId)
            dragged.current = true
        }

        element.addEventListener('pointerdown', onDown, { capture: true })
        window.addEventListener('pointermove', onMove)
        window.addEventListener('pointerup', onUp)
        window.addEventListener('pointercancel', onCancel)
        return () => {
            element.removeEventListener('pointerdown', onDown, { capture: true })
            window.removeEventListener('pointermove', onMove)
            window.removeEventListener('pointerup', onUp)
            window.removeEventListener('pointercancel', onCancel)
        }
    }, [get, dragged])

    const shown = useMemo(
        () => shownMeshes(model, view.hidden, view.isolated),
        [model, view.hidden, view.isolated],
    )

    useLayoutEffect(() => {
        showView(model, shown, view.selected, sketch)
        invalidate()
    }, [model, shown, view.selected, sketch, invalidate])

    const dark = useSyncExternalStore(subscribeToTheme, isDarkTheme)

    useEffect(() => {
        if (!sketch) return
        setSketchColor(sketch, SKETCH_COLORS[dark ? 'dark' : 'light'])
        invalidate()
    }, [sketch, dark, invalidate])

    useEffect(() => {
        const element = get().gl.domElement
        const applyModifier = (modifier: Modifier) => {
            const buttons = controls.current?.mouseButtons
            if (!buttons) return
            const actions = buttonActions(profile, modifier)
            buttons.left = ACTIONS[actions.left]
            buttons.middle = ACTIONS[actions.middle]
            buttons.right = ACTIONS[actions.right]
            buttons.wheel = ACTIONS[actions.wheel]
        }
        const handleModifierEvent = (event: KeyboardEvent | PointerEvent) =>
            applyModifier(activeModifier(event))
        const releaseModifiers = () => applyModifier('plain')

        applyModifier('plain')
        window.addEventListener('keydown', handleModifierEvent)
        window.addEventListener('keyup', handleModifierEvent)
        window.addEventListener('blur', releaseModifiers)
        document.addEventListener('visibilitychange', releaseModifiers)
        // Capture phase runs before camera-controls reads the buttons on pointerdown
        element.addEventListener('pointerdown', handleModifierEvent, { capture: true })
        return () => {
            window.removeEventListener('keydown', handleModifierEvent)
            window.removeEventListener('keyup', handleModifierEvent)
            window.removeEventListener('blur', releaseModifiers)
            document.removeEventListener('visibilitychange', releaseModifiers)
            element.removeEventListener('pointerdown', handleModifierEvent, { capture: true })
        }
    }, [get, profile])

    const resetView = useEffectEvent((transition: boolean) => {
        const visibleWidth = Math.max(size.width - inset.left - inset.right, 1)
        const camera = get().camera as PerspectiveCamera
        const distance = fitDistance(sphere.radius, camera.fov, visibleWidth, size.height)
        const position = ISOMETRIC.clone().multiplyScalar(distance).add(sphere.center)
        const { x, y, z } = sphere.center
        void controls.current?.setLookAt(position.x, position.y, position.z, x, y, z, transition)
        controls.current?.normalizeRotations()
    })

    useEffect(() => {
        resetView(resetCount > 0)
    }, [sphere, resetCount])

    const frameParts = useEffectEvent((targets: string[]) => {
        if (!controls.current) return
        const box = new Box3()
        for (const id of targets) {
            const part = model.parts.get(id)
            if (part) box.expandByObject(part)
        }
        if (box.isEmpty()) return
        const bounds = box.getBoundingSphere(new Sphere())
        const camera = get().camera as PerspectiveCamera
        const visibleWidth = Math.max(size.width - inset.left - inset.right, 1)
        const distance = fitDistance(
            Math.max(bounds.radius, 1e-4),
            camera.fov,
            visibleWidth,
            size.height,
        )
        const target = controls.current.getTarget(new Vector3(), false)
        const position = camera.position
            .clone()
            .sub(target)
            .normalize()
            .multiplyScalar(distance)
            .add(bounds.center)
        const { x, y, z } = bounds.center
        void controls.current.setLookAt(position.x, position.y, position.z, x, y, z, true)
        controls.current.normalizeRotations()
    })

    useEffect(() => {
        if (!frameRequest) return
        // The details panel may open with the selection: wait for the new visible area
        let frame = requestAnimationFrame(() => {
            frame = requestAnimationFrame(() => frameParts(frameRequest.targets))
        })
        return () => cancelAnimationFrame(frame)
    }, [frameRequest])

    const pickPart = (event: ThreeEvent<MouseEvent>) => {
        event.stopPropagation()
        if (dragged.current) return
        const hit = event.intersections.find(({ object }) => {
            const index = model.meshIndex.get(object as Mesh)
            return index !== undefined && shown[index] === 1
        })
        if (hit) onPick(occurrencePath(hit.object))
        else onMiss()
    }

    const lookFrom = (event: ThreeEvent<MouseEvent>) => {
        event.stopPropagation()
        const direction =
            event.object.position.lengthSq() > 0
                ? event.object.position.clone().normalize()
                : event.face?.normal.clone()
        if (!controls.current || !direction) return null
        const target = controls.current.getTarget(new Vector3(), false)
        const position = direction.multiplyScalar(controls.current.distance).add(target)
        void controls.current.setLookAt(
            position.x,
            position.y,
            position.z,
            target.x,
            target.y,
            target.z,
            true,
        )
        controls.current.normalizeRotations()
        return null
    }

    return (
        <>
            <primitive object={model.scene} onClick={pickPart} />
            {sketch ? <primitive object={sketch.lines} /> : null}
            <CameraControls
                ref={controls}
                makeDefault
                dollyToCursor={settings.zoomToCursor}
                azimuthRotateSpeed={speed}
                polarRotateSpeed={speed}
                truckSpeed={2 * speed}
                dollySpeed={settings.invertZoom ? -speed : speed}
            />
            {settings.showViewCube ? (
                <GizmoHelper alignment="bottom-right" margin={[64, 64]}>
                    <GizmoViewcube onClick={lookFrom} />
                </GizmoHelper>
            ) : null}
        </>
    )
}
