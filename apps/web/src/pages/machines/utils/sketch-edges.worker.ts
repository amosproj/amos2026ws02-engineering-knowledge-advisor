import { featureEdges, mergeEdges } from './sketch-edges-model'

export type GeometryItem = { id: number; positions: Float32Array; index: Uint32Array | null }

export type SketchRequest =
    | { type: 'geometries'; items: GeometryItem[] }
    | { type: 'merge'; geometryIds: Int32Array; matrices: Float32Array }

const edgesByGeometry: Float32Array[] = []

self.onmessage = ({ data }: MessageEvent<SketchRequest>) => {
    if (data.type === 'geometries') {
        for (const { id, positions, index } of data.items) {
            edgesByGeometry[id] = featureEdges(positions, index)
        }
        self.postMessage({ type: 'ack' })
        return
    }
    const { positions, offsets } = mergeEdges(edgesByGeometry, data.geometryIds, data.matrices)
    self.postMessage(
        { type: 'merged', positions, offsets },
        { transfer: [positions.buffer, offsets.buffer] },
    )
}
