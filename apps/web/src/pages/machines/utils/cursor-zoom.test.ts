import { CameraControlsImpl } from '@react-three/drei'
import * as THREE from 'three'
import { PerspectiveCamera, Plane, Raycaster, Vector2, Vector3 } from 'three'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { cursorShift } from './cursor-zoom'

describe('cursorShift', () => {
    beforeAll(() => {
        vi.stubGlobal(
            'DOMRect',
            class {
                x = 0
                y = 0
                width = 0
                height = 0
            },
        )
        CameraControlsImpl.install({ THREE })
    })

    it('keeps the point under the cursor in place and the target still while zooming', async () => {
        const camera = new PerspectiveCamera(45, 1.6, 0.01, 1000)
        camera.setViewOffset(1600, 1000, -120, 0, 1600, 1000)
        const controls = new CameraControlsImpl(camera)
        controls.setLookAt(3, 2, 5, 0.2, 0.1, -0.3, false)
        await controls.setFocalOffset(0.4, -0.3, 0, false)
        controls.update(0)
        camera.updateMatrixWorld()
        const cursor = new Vector2(0.55, -0.4)
        const target = controls.getTarget(new Vector3())
        const raycaster = new Raycaster()
        raycaster.setFromCamera(cursor, camera)
        const plane = new Plane().setFromNormalAndCoplanarPoint(
            camera.getWorldDirection(new Vector3()),
            target,
        )
        const point = raycaster.ray.intersectPlane(plane, new Vector3())!

        for (const scale of [0.5, 1.7]) {
            const shift = cursorShift(camera, cursor, controls.distance * (1 - scale))
            const offset = controls.getFocalOffset(new Vector3())
            void controls.dollyTo(controls.distance * scale, false)
            void controls.setFocalOffset(offset.x + shift.x, offset.y + shift.y, offset.z, false)
            controls.update(0)
            camera.updateMatrixWorld()

            const projected = point.clone().project(camera)
            expect(projected.x).toBeCloseTo(cursor.x, 6)
            expect(projected.y).toBeCloseTo(cursor.y, 6)
            expect(controls.getTarget(new Vector3()).distanceTo(target)).toBeCloseTo(0, 9)
        }
    })
})
