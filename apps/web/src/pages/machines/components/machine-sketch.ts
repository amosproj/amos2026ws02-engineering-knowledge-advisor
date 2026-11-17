import {
    BufferAttribute,
    BufferGeometry,
    LineBasicMaterial,
    LineSegments,
    type Mesh,
    type Object3D,
} from 'three'

import type { GeometryItem, SketchRequest } from './sketch-edges.worker'

// Floats copied to the worker per message, bounds the memory held by pending copies
const BATCH_FLOATS = 6_000_000

export type Sketch = {
    lines: LineSegments<BufferGeometry, LineBasicMaterial[]>
    offsets: Uint32Array
}

type SketchReply =
    { type: 'ack' } | { type: 'merged'; positions: Float32Array; offsets: Uint32Array }

// Computes the edges in a worker. meshes must be in scene traversal order
export async function buildSketch(scene: Object3D, meshes: Mesh[], signal: AbortSignal) {
    signal.throwIfAborted()
    scene.updateMatrixWorld(true)
    const geometryIds = new Map<BufferGeometry, number>()
    const meshGeometries = new Int32Array(meshes.length)
    const matrices = new Float32Array(meshes.length * 16)
    meshes.forEach((mesh, i) => {
        let id = geometryIds.get(mesh.geometry)
        if (id === undefined) {
            id = geometryIds.size
            geometryIds.set(mesh.geometry, id)
        }
        meshGeometries[i] = id
        matrices.set(mesh.matrixWorld.elements, i * 16)
    })

    const worker = new Worker(new URL('./sketch-edges.worker.ts', import.meta.url), {
        type: 'module',
    })
    const aborted = new Promise<never>((_, reject) =>
        signal.addEventListener('abort', () => reject(signal.reason), { once: true }),
    )
    const send = (request: SketchRequest, transfer: Transferable[]) => {
        const reply = new Promise<SketchReply>((resolve, reject) => {
            worker.onmessage = (event: MessageEvent<SketchReply>) => resolve(event.data)
            worker.onerror = (event) => reject(new Error(event.message))
        })
        worker.postMessage(request, transfer)
        return Promise.race([reply, aborted])
    }

    try {
        let batch: GeometryItem[] = []
        let floats = 0
        const flush = async () => {
            if (batch.length === 0) return
            const transfer = batch.flatMap(({ positions, index }) =>
                index ? [positions.buffer, index.buffer] : [positions.buffer],
            )
            await send({ type: 'geometries', items: batch }, transfer)
            batch = []
            floats = 0
        }
        for (const [geometry, id] of geometryIds) {
            const item = { id, positions: copyPositions(geometry), index: copyIndex(geometry) }
            batch.push(item)
            floats += item.positions.length
            if (floats >= BATCH_FLOATS) await flush()
        }
        await flush()
        const reply = await send({ type: 'merge', geometryIds: meshGeometries, matrices }, [
            meshGeometries.buffer,
            matrices.buffer,
        ])
        if (reply.type !== 'merged') throw new Error('Unexpected reply from the sketch worker')
        return createSketch(reply.positions, reply.offsets)
    } finally {
        worker.terminate()
    }
}

// Copies: transferring the live buffers would detach them from the rendered geometry
function copyPositions(geometry: BufferGeometry) {
    const attribute = geometry.getAttribute('position')
    const positions = new Float32Array(attribute.count * 3)
    for (let i = 0; i < attribute.count; i++) {
        positions[i * 3] = attribute.getX(i)
        positions[i * 3 + 1] = attribute.getY(i)
        positions[i * 3 + 2] = attribute.getZ(i)
    }
    return positions
}

function copyIndex(geometry: BufferGeometry) {
    return geometry.index ? Uint32Array.from(geometry.index.array) : null
}

function createSketch(positions: Float32Array, offsets: Uint32Array): Sketch {
    const geometry = new BufferGeometry()
    geometry.setAttribute('position', new BufferAttribute(positions, 3))
    // Drawn over the solid selection without hiding its surface, which still hides the lines behind
    const material = new LineBasicMaterial({ depthWrite: false })
    const lines = new LineSegments(geometry, [material])
    lines.raycast = () => {}
    lines.renderOrder = 1
    lines.visible = false
    return { lines, offsets }
}

export function setSketchColor({ lines }: Sketch, color: string) {
    for (const material of lines.material) material.color.set(color)
}

export function disposeSketch({ lines }: Sketch) {
    lines.geometry.dispose()
    for (const material of lines.material) material.dispose()
}

export function showSketch({ lines, offsets }: Sketch, drawn: Uint8Array) {
    const { geometry } = lines
    geometry.clearGroups()
    let start: number | undefined
    const addRange = (end: number) => {
        if (start !== undefined) geometry.addGroup(start, end - start, 0)
        start = undefined
    }
    drawn.forEach((flag, mesh) => {
        // Meshes without edges neither split nor extend a range
        if (offsets[mesh] === offsets[mesh + 1]) return
        if (flag) start ??= offsets[mesh]
        else addRange(offsets[mesh])
    })
    addRange(offsets[drawn.length])
    lines.visible = geometry.groups.length > 0
}
