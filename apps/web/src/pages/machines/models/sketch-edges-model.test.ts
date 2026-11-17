import { BoxGeometry, CylinderGeometry, type BufferGeometry } from 'three'
import { describe, expect, it } from 'vitest'

import { featureEdges } from './sketch-edges-model'

function edgeCount(geometry: BufferGeometry) {
    const positions = geometry.getAttribute('position').array as Float32Array
    const index = geometry.index ? Uint32Array.from(geometry.index.array) : null
    return featureEdges(positions, index).length / 6
}

describe('featureEdges', () => {
    it('keeps the edges of a part smaller than the welding grid', () => {
        expect(edgeCount(new BoxGeometry(1e-5, 1e-5, 1e-5))).toBe(12)
    })

    it('draws no line between the facets of a curved face', () => {
        // 13 segments: about 28° between facets, as the GLB generator produces
        expect(edgeCount(new CylinderGeometry(1, 1, 1, 13))).toBe(26)
    })
})
