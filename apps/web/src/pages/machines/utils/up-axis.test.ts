import { Vector3 } from 'three'
import { expect, it } from 'vitest'

import { upAxis, type UpAxis } from '../query/machine-api'
import { UP_AXIS_ROTATIONS } from './up-axis'

// Directions of the CAD axes in the GLB
const SCENE_DIRECTIONS: Record<UpAxis, [number, number, number]> = {
    X: [1, 0, 0],
    Y: [0, 0, -1],
    Z: [0, 1, 0],
    '-X': [-1, 0, 0],
    '-Y': [0, 0, 1],
    '-Z': [0, -1, 0],
}

it.each(upAxis.options)('turns %s of the CAD file upwards', (axis) => {
    const direction = new Vector3(...SCENE_DIRECTIONS[axis])
    direction.applyQuaternion(UP_AXIS_ROTATIONS[axis])
    expect(direction.distanceTo(new Vector3(0, 1, 0))).toBeCloseTo(0)
})
