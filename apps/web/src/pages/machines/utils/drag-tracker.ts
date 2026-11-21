// Pointer travel in pixels beyond which a press is a camera drag, not a click
const CLICK_TOLERANCE = 4

export function trackDrag(element: HTMLElement, dragged: { current: boolean }) {
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
}
