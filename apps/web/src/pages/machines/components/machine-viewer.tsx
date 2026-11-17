import { useEffect, useEffectEvent, useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CameraControls, CameraControlsImpl, GizmoHelper, GizmoViewcube } from '@react-three/drei'
import { Canvas, useThree, type ThreeEvent } from '@react-three/fiber'
import {
    Box3,
    Mesh,
    PerspectiveCamera,
    PMREMGenerator,
    Sphere,
    Texture,
    Vector3,
    type Object3D,
} from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'

import { Home09Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import { Button, Spinner } from '@components'

import { errorCode } from '../models/machine-errors'
import { DEFAULT_MOUSE_PROFILE, type MouseAction } from '../models/mouse-profile-model'
import { fitDistance, visibleCenterShift, type ViewInset } from '../models/viewer-camera-model'
import { fetchModel } from '../query/machine-api'

const { ACTION } = CameraControlsImpl
const ACTIONS: Record<MouseAction, 0 | 1 | 2 | 16> = {
    rotate: ACTION.ROTATE,
    pan: ACTION.TRUCK,
    zoom: ACTION.DOLLY,
    none: ACTION.NONE,
}
const MOUSE_BUTTONS = {
    left: ACTIONS[DEFAULT_MOUSE_PROFILE.left],
    middle: ACTIONS[DEFAULT_MOUSE_PROFILE.middle],
    right: ACTIONS[DEFAULT_MOUSE_PROFILE.right],
    wheel: ACTIONS[DEFAULT_MOUSE_PROFILE.wheel],
}
const ISOMETRIC = new Vector3(1, 0.8, 1).normalize()
const FOV = 45

const loader = new GLTFLoader()

type Model = { scene: Object3D; sphere: Sphere | null }

async function loadModel(fileId: string, signal: AbortSignal): Promise<Model> {
    const gltf = await loader.parseAsync(await fetchModel(fileId, signal), '')
    if (signal.aborted) {
        disposeModel(gltf.scene)
        throw signal.reason
    }
    const box = new Box3().setFromObject(gltf.scene)
    if (box.isEmpty()) return { scene: gltf.scene, sphere: null }
    const sphere = box.getBoundingSphere(new Sphere())
    sphere.radius = Math.max(sphere.radius, 1e-3)
    return { scene: gltf.scene, sphere }
}

function disposeModel(scene: Object3D) {
    scene.traverse((object) => {
        if (!(object instanceof Mesh)) return
        object.geometry.dispose()
        for (const material of [object.material].flat()) {
            for (const value of Object.values(material)) {
                if (value instanceof Texture) value.dispose()
            }
            material.dispose()
        }
    })
}

type MachineViewerProps = { fileId: string; inset: ViewInset }

export default function MachineViewer({ fileId, inset }: MachineViewerProps) {
    const model = useQuery({
        queryKey: ['models', fileId],
        queryFn: ({ signal }) => loadModel(fileId, signal),
        staleTime: Infinity,
        gcTime: 0,
    })
    const [resetCount, setResetCount] = useState(0)
    const scene = model.data?.scene

    useEffect(() => {
        if (!scene) return
        return () => disposeModel(scene)
    }, [scene])

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
    if (!model.data.sphere) {
        return <Overlay inset={inset}>The 3D model is empty.</Overlay>
    }

    return (
        <>
            <Canvas flat frameloop="demand" dpr={[1, 2]} camera={{ fov: FOV }}>
                <Lighting />
                <Scene
                    scene={model.data.scene}
                    sphere={model.data.sphere}
                    inset={inset}
                    resetCount={resetCount}
                />
            </Canvas>
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
    scene: Object3D
    sphere: Sphere
    inset: ViewInset
    resetCount: number
}

function Scene({ scene, sphere, inset, resetCount }: SceneProps) {
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
        const camera = get().camera as PerspectiveCamera
        camera.near = sphere.radius * 0.005
        camera.far = sphere.radius * 200
        camera.updateProjectionMatrix()
        if (controls.current) {
            controls.current.minDistance = sphere.radius * 0.02
            controls.current.maxDistance = sphere.radius * 50
        }
    }, [get, sphere])

    const resetView = useEffectEvent((transition: boolean) => {
        const visibleWidth = Math.max(size.width - inset.left - inset.right, 1)
        const camera = get().camera as PerspectiveCamera
        const distance = fitDistance(sphere.radius, camera.fov, visibleWidth, size.height)
        const position = ISOMETRIC.clone().multiplyScalar(distance).add(sphere.center)
        const { x, y, z } = sphere.center
        void controls.current?.setLookAt(position.x, position.y, position.z, x, y, z, transition)
    })

    useEffect(() => {
        resetView(resetCount > 0)
    }, [sphere, resetCount])

    const lookFrom = (event: ThreeEvent<MouseEvent>) => {
        event.stopPropagation()
        const direction =
            event.object.position.lengthSq() > 0
                ? event.object.position.clone().normalize()
                : event.face?.normal.clone()
        if (!controls.current || !direction) return null
        const target = controls.current.getTarget(new Vector3())
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
        return null
    }

    return (
        <>
            <primitive object={scene} />
            <CameraControls ref={controls} makeDefault dollyToCursor mouseButtons={MOUSE_BUTTONS} />
            <GizmoHelper alignment="bottom-right" margin={[64, 64]}>
                <GizmoViewcube onClick={lookFrom} />
            </GizmoHelper>
        </>
    )
}
