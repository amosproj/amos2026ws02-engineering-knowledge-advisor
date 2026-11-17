/** Canvas pixels hidden by the floating panels on each side. */
export type ViewInset = { left: number; right: number }

const FIT_MARGIN = 1.15

export function fitDistance(radius: number, fovDegrees: number, width: number, height: number) {
    const halfVertical = (fovDegrees * Math.PI) / 360
    const halfHorizontal = Math.atan((Math.tan(halfVertical) * width) / height)
    return (radius / Math.sin(Math.min(halfVertical, halfHorizontal))) * FIT_MARGIN
}

export function visibleCenterShift(inset: ViewInset) {
    return (inset.left - inset.right) / 2
}
