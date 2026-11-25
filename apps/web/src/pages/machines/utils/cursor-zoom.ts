import { CameraControlsImpl } from '@react-three/drei'
import { MathUtils, Spherical, Vector2, Vector3, type PerspectiveCamera } from 'three'

const { ACTION } = CameraControlsImpl
const DOLLY_ACTIONS =
    ACTION.DOLLY |
    ACTION.TOUCH_DOLLY |
    ACTION.TOUCH_DOLLY_TRUCK |
    ACTION.TOUCH_DOLLY_SCREEN_PAN |
    ACTION.TOUCH_DOLLY_OFFSET |
    ACTION.TOUCH_DOLLY_ROTATE

type Point = { x: number; y: number }

/**
 * Focal offset change that keeps the point under the cursor in place on the target's depth
 * plane when the distance to the target shrinks by radiusChange. cursor is in NDC.
 */
export function cursorShift(camera: PerspectiveCamera, cursor: Vector2, radiusChange: number) {
    const center = camera.getWorldDirection(new Vector3()).add(camera.position).project(camera)
    const halfHeight = Math.tan(MathUtils.degToRad(camera.getEffectiveFOV() / 2))
    return new Vector2(
        (cursor.x - center.x) * halfHeight * camera.aspect * radiusChange,
        -(cursor.y - center.y) * halfHeight * radiusChange,
    )
}

/** Zooms toward the cursor by shifting the view, the orbit target stays where it is. */
export class CursorZoom {
    private readonly internals: { _isUserControllingOffset: boolean }
    private readonly pointers = new Map<number, Point>()
    private readonly spherical = new Spherical()
    private readonly offset = new Vector3()
    // Trackpad pinch delta per wheel notch, as camera-controls reads it
    private readonly pinchDelta = /Mac/.test(navigator.userAgent) ? 10 : 30
    private press: Point = { x: 0, y: 0 }
    private cursor: Point = { x: 0, y: 0 }
    private wheeled = false
    private radius: number

    private readonly controls: CameraControlsImpl
    private readonly camera: PerspectiveCamera
    private readonly element: HTMLElement
    private readonly invalidate: () => void

    constructor(
        controls: CameraControlsImpl,
        camera: PerspectiveCamera,
        element: HTMLElement,
        invalidate: () => void,
    ) {
        this.controls = controls
        this.camera = camera
        this.element = element
        this.invalidate = invalidate
        this.internals = controls as unknown as { _isUserControllingOffset: boolean }
        this.radius = this.targetRadius()

        // Capture phase runs before camera-controls handles the event
        element.addEventListener('wheel', this.onWheel, { capture: true, passive: false })
        element.addEventListener('pointerdown', this.onDown, { capture: true })
        window.addEventListener('pointermove', this.onMove, { capture: true })
        window.addEventListener('pointerup', this.onUp, { capture: true })
        window.addEventListener('pointercancel', this.onUp, { capture: true })
        controls.addEventListener('controlstart', this.onControlStart)
        controls.addEventListener('control', this.onControl)
    }

    dispose() {
        this.element.removeEventListener('wheel', this.onWheel, { capture: true })
        this.element.removeEventListener('pointerdown', this.onDown, { capture: true })
        window.removeEventListener('pointermove', this.onMove, { capture: true })
        window.removeEventListener('pointerup', this.onUp, { capture: true })
        window.removeEventListener('pointercancel', this.onUp, { capture: true })
        this.controls.removeEventListener('controlstart', this.onControlStart)
        this.controls.removeEventListener('control', this.onControl)
    }

    private targetRadius() {
        return this.controls.getSpherical(this.spherical, true).radius
    }

    private shiftView(radiusChange: number, { x, y }: Point) {
        const rect = this.element.getBoundingClientRect()
        const cursor = new Vector2(
            ((x - rect.left) / rect.width) * 2 - 1,
            -((y - rect.top) / rect.height) * 2 + 1,
        )
        const shift = cursorShift(this.camera, cursor, radiusChange)
        const offset = this.controls.getFocalOffset(this.offset, true)
        void this.controls.setFocalOffset(offset.x + shift.x, offset.y + shift.y, offset.z, true)
    }

    private followPointers() {
        let x = 0
        let y = 0
        for (const point of this.pointers.values()) {
            x += point.x / this.pointers.size
            y += point.y / this.pointers.size
        }
        this.cursor = { x, y }
    }

    private readonly onWheel = (event: WheelEvent) => {
        this.cursor = { x: event.clientX, y: event.clientY }
        this.wheeled = true
        this.radius = this.targetRadius()
        if (!event.ctrlKey) return
        // camera-controls zooms the lens on a trackpad pinch: dolly instead, like the wheel
        event.preventDefault()
        event.stopImmediatePropagation()
        const scale = Math.pow(0.95, (-event.deltaY / this.pinchDelta) * this.controls.dollySpeed)
        void this.controls.dollyTo(this.radius * scale, true)
        this.shiftView(this.radius - this.targetRadius(), this.cursor)
        this.radius = this.targetRadius()
        this.invalidate()
    }

    private readonly onDown = (event: PointerEvent) => {
        this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
        this.press = { x: event.clientX, y: event.clientY }
        this.wheeled = false
        this.followPointers()
    }

    private readonly onMove = (event: PointerEvent) => {
        if (!this.pointers.has(event.pointerId)) return
        this.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
        this.wheeled = false
        this.followPointers()
    }

    private readonly onUp = (event: PointerEvent) => {
        this.pointers.delete(event.pointerId)
        this.followPointers()
        this.radius = this.targetRadius()
    }

    private readonly onControlStart = () => {
        this.radius = this.targetRadius()
        if ((this.controls.currentAction & DOLLY_ACTIONS) === 0) return
        // camera-controls stops the zoom where it is: stop the screen shift with it
        const offset = this.controls.getFocalOffset(this.offset, false)
        void this.controls.setFocalOffset(offset.x, offset.y, offset.z, false)
    }

    private readonly onControl = () => {
        const next = this.targetRadius()
        const change = this.radius - next
        this.radius = next
        if (change === 0) return
        const dragDolly = !this.wheeled && (this.controls.currentAction & ACTION.DOLLY) !== 0
        this.shiftView(change, dragDolly ? this.press : this.cursor)
        // Same damping as the user zoom, otherwise the point drifts during the animation
        this.internals._isUserControllingOffset = true
    }
}
