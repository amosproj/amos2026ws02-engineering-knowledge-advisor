import {
    useEffect,
    useEffectEvent,
    useLayoutEffect,
    useMemo,
    useRef,
    useState,
    useSyncExternalStore,
} from 'react'
import { CameraControls, CameraControlsImpl, GizmoHelper, GizmoViewcube } from '@react-three/drei'
import { useThree, type ThreeEvent } from '@react-three/fiber'
import type { PerspectiveCamera, Quaternion, Sphere } from 'three'

import { useSettings } from '@components'
import type { NavigationSpeed } from '@pages/settings/models/settings-model'

import { MOUSE_PROFILES, activeModifier, buttonActions } from '../models/mouse-profile-model'
import { CameraRig, type ViewInset } from '../utils/camera-rig'
import { CursorZoom } from '../utils/cursor-zoom'
import { trackDrag } from '../utils/drag-tracker'
import { setSketchColor, type Sketch } from '../utils/machine-sketch'
import type { SceneModel } from '../utils/scene-model'
import type { FrameRequest, ViewState } from './machine-viewer'

const SPEED_FACTORS: Record<NavigationSpeed, number> = { slow: 0.5, normal: 1, fast: 2 }
const SKETCH_COLORS = { light: '#8f8f8f', dark: '#6e6e6e' }

function subscribeToTheme(onChange: () => void) {
    const observer = new MutationObserver(onChange)
    observer.observe(document.documentElement, { attributeFilter: ['class'] })
    return () => observer.disconnect()
}

const isDarkTheme = () => document.documentElement.classList.contains('dark')

type ViewerSceneProps = {
    model: SceneModel
    rotation: Quaternion
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

export function ViewerScene({
    model,
    rotation,
    sphere,
    inset,
    resetCount,
    view,
    frameRequest,
    sketch,
    dragged,
    onPick,
    onMiss,
}: ViewerSceneProps) {
    const { settings } = useSettings()
    const profile = MOUSE_PROFILES[settings.mouseProfile]
    const speed = SPEED_FACTORS[settings.navigationSpeed]
    const controls = useRef<CameraControlsImpl>(null)
    const [rig, setRig] = useState<CameraRig>()
    const get = useThree((state) => state.get)
    const size = useThree((state) => state.size)
    const invalidate = useThree((state) => state.invalidate)

    useLayoutEffect(() => {
        if (!controls.current) return
        const cameraRig = new CameraRig(controls.current, get().camera as PerspectiveCamera)
        setRig(cameraRig)
        return () => cameraRig.dispose()
    }, [get])

    useLayoutEffect(() => {
        rig?.setInset(inset, size)
        invalidate()
    }, [rig, size, inset, invalidate])

    useEffect(() => rig?.fitToModel(sphere), [rig, sphere])

    useEffect(() => rig?.setPanSpeed(speed), [rig, speed])

    useEffect(() => trackDrag(get().gl.domElement, dragged), [get, dragged])

    useEffect(() => {
        if (!controls.current || !settings.zoomToCursor) return
        const { camera, gl } = get()
        const zoom = new CursorZoom(
            controls.current,
            camera as PerspectiveCamera,
            gl.domElement,
            invalidate,
        )
        return () => zoom.dispose()
    }, [get, invalidate, settings.zoomToCursor])

    useEffect(() => {
        if (!rig) return
        const element = get().gl.domElement
        const applyModifier = (event?: KeyboardEvent | PointerEvent) =>
            rig.setMouseActions(buttonActions(profile, event ? activeModifier(event) : 'plain'))
        const releaseModifiers = () => applyModifier()

        applyModifier()
        window.addEventListener('keydown', applyModifier)
        window.addEventListener('keyup', applyModifier)
        window.addEventListener('blur', releaseModifiers)
        document.addEventListener('visibilitychange', releaseModifiers)
        // Capture phase runs before camera-controls reads the buttons on pointerdown
        element.addEventListener('pointerdown', applyModifier, { capture: true })
        return () => {
            window.removeEventListener('keydown', applyModifier)
            window.removeEventListener('keyup', applyModifier)
            window.removeEventListener('blur', releaseModifiers)
            document.removeEventListener('visibilitychange', releaseModifiers)
            element.removeEventListener('pointerdown', applyModifier, { capture: true })
        }
    }, [get, rig, profile])

    const shown = useMemo(
        () => model.shownMask(view.hidden, view.isolated),
        [model, view.hidden, view.isolated],
    )

    useLayoutEffect(() => {
        model.applyView(shown, view.selected, sketch)
        invalidate()
    }, [model, shown, view.selected, sketch, invalidate])

    const dark = useSyncExternalStore(subscribeToTheme, isDarkTheme)

    useEffect(() => {
        if (!sketch) return
        setSketchColor(sketch, SKETCH_COLORS[dark ? 'dark' : 'light'])
        invalidate()
    }, [sketch, dark, invalidate])

    const resetView = useEffectEvent((transition: boolean) => {
        rig?.reset(sphere, inset, size, transition)
    })

    useEffect(() => {
        resetView(false)
    }, [rig, sphere])

    useEffect(() => {
        if (resetCount > 0) resetView(true)
    }, [resetCount])

    const frameParts = useEffectEvent((targets: string[]) => {
        const bounds = model.partsBounds(targets)
        if (bounds) rig?.frame(bounds, inset, size)
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
        const path = model.pickedPath(event.intersections, shown)
        if (path) onPick(path)
        else onMiss()
    }

    const lookFrom = (event: ThreeEvent<MouseEvent>) => {
        event.stopPropagation()
        const direction =
            event.object.position.lengthSq() > 0
                ? event.object.position.clone().normalize()
                : event.face?.normal.clone()
        if (direction) rig?.lookFrom(direction)
        return null
    }

    return (
        <>
            <group quaternion={rotation}>
                <primitive object={model.scene} onClick={pickPart} />
                {sketch ? <primitive object={sketch.lines} /> : null}
            </group>
            <CameraControls
                ref={controls}
                makeDefault
                azimuthRotateSpeed={speed}
                polarRotateSpeed={speed}
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
