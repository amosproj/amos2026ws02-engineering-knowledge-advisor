import { BufferAttribute, BufferGeometry, EdgesGeometry, Matrix4, Vector3 } from 'three'

/**
 * Minimum angle in degrees between two faces for their shared edge to be drawn.
 * Above the 29° the GLB generator allows between facets, so curved faces show no facets.
 */
export const EDGE_THRESHOLD = 40

export function featureEdges(positions: Float32Array, index: Uint32Array | null) {
    // EdgesGeometry welds vertices on a 1e-4 grid, in meters it would erase sub-millimeter details
    const min = [Infinity, Infinity, Infinity]
    const max = [-Infinity, -Infinity, -Infinity]
    for (let i = 0; i < positions.length; i++) {
        min[i % 3] = Math.min(min[i % 3], positions[i])
        max[i % 3] = Math.max(max[i % 3], positions[i])
    }
    const center = min.map((value, axis) => (value + max[axis]) / 2)
    const scale = Math.max(...max.map((value, axis) => value - min[axis])) || 1
    const normalized = positions.map((value, i) => (value - center[i % 3]) / scale)

    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new BufferAttribute(normalized, 3))
    if (index) geometry.setIndex(new BufferAttribute(index, 1))
    const edges = new EdgesGeometry(geometry, EDGE_THRESHOLD)
    const result = (edges.getAttribute('position').array as Float32Array).map(
        (value, i) => value * scale + center[i % 3],
    )
    geometry.dispose()
    edges.dispose()
    return result
}

/**
 * ``offsets[i]`` is the first vertex of mesh ``i``, ``offsets[n]`` the vertex count.
 */
export function mergeEdges(
    edgesByGeometry: Float32Array[],
    geometryIds: Int32Array,
    matrices: Float32Array,
) {
    const offsets = new Uint32Array(geometryIds.length + 1)
    geometryIds.forEach((id, mesh) => {
        offsets[mesh + 1] = offsets[mesh] + edgesByGeometry[id].length / 3
    })
    const positions = new Float32Array(offsets[geometryIds.length] * 3)
    const matrix = new Matrix4()
    const vertex = new Vector3()
    geometryIds.forEach((id, mesh) => {
        matrix.fromArray(matrices, mesh * 16)
        const edges = edgesByGeometry[id]
        const start = offsets[mesh] * 3
        for (let i = 0; i < edges.length; i += 3) {
            vertex
                .fromArray(edges, i)
                .applyMatrix4(matrix)
                .toArray(positions, start + i)
        }
    })
    return { positions, offsets }
}
