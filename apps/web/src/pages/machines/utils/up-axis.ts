import { Quaternion, Vector3 } from 'three'

import type { UpAxis } from '../query/machine-api'

const rotation = (axis: [number, number, number], degrees: number) =>
    new Quaternion().setFromAxisAngle(new Vector3(...axis), (degrees * Math.PI) / 180)

// The GLB is written for CAD files with Z up: X, Y, Z of the CAD file are X, -Z, Y of the scene
export const UP_AXIS_ROTATIONS: Record<UpAxis, Quaternion> = {
    X: rotation([0, 0, 1], 90),
    Y: rotation([1, 0, 0], 90),
    Z: new Quaternion(),
    '-X': rotation([0, 0, 1], -90),
    '-Y': rotation([1, 0, 0], -90),
    '-Z': rotation([1, 0, 0], 180),
}
