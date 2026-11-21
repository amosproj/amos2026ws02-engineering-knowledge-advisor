import { CameraControlsImpl } from '@react-three/drei'
import { Vector3, type PerspectiveCamera, type Sphere } from 'three'

import type { MouseAction } from '../models/mouse-profile-model'

export type ViewInset = { left: number; right: number }

export type ViewSize = { width: number; height: number }

const { ACTION } = CameraControlsImpl
// Pan shifts the view on screen without moving the orbit target: the model keeps rotating
// around its own center, or around the framed parts
const ACTIONS: Record<MouseAction, 0 | 1 | 8 | 16> = {
    rotate: ACTION.ROTATE,
    pan: ACTION.OFFSET,
    zoom: ACTION.DOLLY,
    none: ACTION.NONE,
}
const ISOMETRIC = new Vector3(1, 0.8, 1).normalize()
const FIT_MARGIN = 1.15

export function fitDistance(radius: number, fovDegrees: number, width: number, height: number) {
    const halfVertical = (fovDegrees * Math.PI) / 360
    const halfHorizontal = Math.atan((Math.tan(halfVertical) * width) / height)
    return (radius / Math.sin(Math.min(halfVertical, halfHorizontal))) * FIT_MARGIN
}

export class CameraRig {
    private sphere: Sphere | undefined
    private panSpeed = 1
    private readonly target = new Vector3()

    private readonly controls: CameraControlsImpl
    private readonly camera: PerspectiveCamera

    constructor(controls: CameraControlsImpl, camera: PerspectiveCamera) {
        this.controls = controls
        this.camera = camera
        controls.touches.two = ACTION.TOUCH_DOLLY_OFFSET
        controls.touches.three = ACTION.TOUCH_OFFSET
        controls.addEventListener('update', this.onUpdate)
    }

    dispose() {
        this.controls.removeEventListener('update', this.onUpdate)
    }

    setInset(inset: ViewInset, size: ViewSize) {
        const shift = inset.left / 2
        this.camera.setViewOffset(size.width, size.height, -shift, 0, size.width, size.height)
        this.controls.setViewport(shift, 0, size.width, size.height)
    }

    fitToModel(sphere: Sphere) {
        this.sphere = sphere
        // Small enough to frame a screw of a large machine
        this.controls.minDistance = sphere.radius * 1e-4
        this.controls.maxDistance = sphere.radius * 50
        this.onUpdate()
    }

    setPanSpeed(speed: number) {
        this.panSpeed = speed
        this.onUpdate()
    }

    setMouseActions(actions: Record<'left' | 'middle' | 'right' | 'wheel', MouseAction>) {
        const buttons = this.controls.mouseButtons
        buttons.left = ACTIONS[actions.left]
        buttons.middle = ACTIONS[actions.middle]
        buttons.right = ACTIONS[actions.right]
        buttons.wheel = ACTIONS[actions.wheel]
    }

    reset(sphere: Sphere, inset: ViewInset, size: ViewSize, transition: boolean) {
        const distance = this.fitDistance(sphere.radius, inset, size)
        this.lookAt(
            ISOMETRIC.clone().multiplyScalar(distance).add(sphere.center),
            sphere.center,
            transition,
            this.detailsShift(distance, inset, size),
        )
    }

    frame(bounds: Sphere, inset: ViewInset, size: ViewSize) {
        const distance = this.fitDistance(Math.max(bounds.radius, 1e-4), inset, size)
        const position = this.camera
            .getWorldDirection(new Vector3())
            .negate()
            .multiplyScalar(distance)
            .add(bounds.center)
        this.lookAt(position, bounds.center, true, this.detailsShift(distance, inset, size))
    }

    lookFrom(direction: Vector3) {
        const target = this.controls.getTarget(new Vector3(), true)
        const position = direction.clone().multiplyScalar(this.controls.distance).add(target)
        this.lookAt(position, target, true)
    }

    private lookAt(position: Vector3, target: Vector3, transition: boolean, shift = 0) {
        void this.controls.setLookAt(
            position.x,
            position.y,
            position.z,
            target.x,
            target.y,
            target.z,
            transition,
        )
        void this.controls.setFocalOffset(shift, 0, 0, transition)
        this.controls.normalizeRotations()
    }

    private detailsShift(distance: number, inset: ViewInset, size: ViewSize) {
        const worldPerPixel =
            (2 * distance * Math.tan((this.camera.fov * Math.PI) / 360)) / size.height
        return (inset.right / 2) * worldPerPixel
    }

    private fitDistance(radius: number, inset: ViewInset, size: ViewSize) {
        const visibleWidth = Math.max(size.width - inset.left - inset.right, 1)
        return fitDistance(radius, this.camera.fov, visibleWidth, size.height)
    }

    private readonly onUpdate = () => {
        const { camera, controls, sphere } = this
        if (sphere) {
            // Follows the distance, a fixed near plane would clip small parts seen up close
            camera.near = controls.distance * 0.01
            camera.far = camera.position.distanceTo(sphere.center) + sphere.radius * 2
            camera.updateProjectionMatrix()
        }
        // Pan speed follows the distance to the target, which a large screen shift inflates
        const distance = camera.position.distanceTo(controls.getTarget(this.target, false))
        controls.truckSpeed =
            distance > 0 ? (2 * this.panSpeed * controls.distance) / distance : 2 * this.panSpeed
    }
}
