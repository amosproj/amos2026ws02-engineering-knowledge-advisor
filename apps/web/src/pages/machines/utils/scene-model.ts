import {
    Box3,
    Color,
    Mesh,
    Sphere,
    Texture,
    type Intersection,
    type Material,
    type Object3D,
} from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

import { fetchModel } from '../query/machine-api'
import { showSketch, type Sketch } from './machine-sketch'

const HIGHLIGHT = new Color('#2563eb')

const loader = new GLTFLoader()

export class SceneModel {
    readonly scene: Object3D
    readonly parts: Map<string, Object3D>
    // In scene traversal order: the meshes of a part follow each other
    readonly meshes: Mesh[]
    sphere: Sphere | null = null
    private readonly ranges: Map<string, [number, number]>
    private readonly meshIndex: Map<Mesh, number>
    private readonly originals: (Material | Material[])[]
    private readonly highlights = new Map<Material, Material>()

    private constructor(
        scene: Object3D,
        parts: Map<string, Object3D>,
        meshes: Mesh[],
        ranges: Map<string, [number, number]>,
    ) {
        this.scene = scene
        this.parts = parts
        this.meshes = meshes
        this.ranges = ranges
        this.meshIndex = new Map(meshes.map((mesh, i) => [mesh, i]))
        this.originals = meshes.map((mesh) => mesh.material)
    }

    static async load(fileId: string, signal: AbortSignal) {
        const gltf = await loader.parseAsync(await fetchModel(fileId, signal), '')
        const parts = new Map<string, Object3D>()
        const meshes: Mesh[] = []
        const ranges = new Map<string, [number, number]>()
        const walk = (object: Object3D) => {
            const start = meshes.length
            if (object instanceof Mesh) meshes.push(object)
            for (const child of object.children) walk(child)
            const id: unknown = object.userData.occurrenceId
            if (typeof id === 'string') {
                parts.set(id, object)
                ranges.set(id, [start, meshes.length])
            }
        }
        walk(gltf.scene)
        const model = new SceneModel(gltf.scene, parts, meshes, ranges)
        if (signal.aborted) {
            model.dispose()
            throw signal.reason
        }
        const box = new Box3().setFromObject(gltf.scene)
        if (box.isEmpty()) return model
        model.sphere = box.getBoundingSphere(new Sphere())
        model.sphere.radius = Math.max(model.sphere.radius, 1e-3)
        return model
    }

    shownMask(hidden: string[], isolated: string[] | undefined) {
        const shown = new Uint8Array(this.meshes.length).fill(isolated ? 0 : 1)
        if (isolated) this.fillRanges(shown, isolated, 1)
        this.fillRanges(shown, hidden, 0)
        return shown
    }

    applyView(shown: Uint8Array, selectedIds: string[], sketch?: Sketch) {
        const selected = new Uint8Array(this.meshes.length)
        this.fillRanges(selected, selectedIds, 1)

        // A hidden selection leaves the shown meshes solid instead of turning them all to edges
        const sketching = sketch !== undefined && selected.some((flag, i) => flag && shown[i])
        const drawn = new Uint8Array(this.meshes.length)
        this.meshes.forEach((mesh, i) => {
            const original = this.originals[i]
            const highlighted = shown[i] && selected[i]

            // Meshes hidden for the sketch still catch clicks: the raycaster ignores visibility
            mesh.visible = Boolean(shown[i] && (!sketching || selected[i]))
            mesh.material =
                sketching || !highlighted
                    ? original
                    : Array.isArray(original)
                      ? original.map((material) => this.highlightOf(material))
                      : this.highlightOf(original)
            drawn[i] = sketching && shown[i] && !selected[i] ? 1 : 0
        })
        if (sketch) showSketch(sketch, drawn)
    }

    partsBounds(ids: string[]) {
        const box = new Box3()
        for (const id of ids) {
            const part = this.parts.get(id)
            if (!part) continue
            part.updateWorldMatrix(true, false)
            box.expandByObject(part)
        }
        return box.isEmpty() ? undefined : box.getBoundingSphere(new Sphere())
    }

    pickedPath(intersections: Intersection[], shown: Uint8Array) {
        const hit = intersections.find(({ object }) => {
            const index = this.meshIndex.get(object as Mesh)
            return index !== undefined && shown[index] === 1
        })
        if (!hit) return undefined
        const ids: string[] = []
        for (let object: Object3D | null = hit.object; object; object = object.parent) {
            const id: unknown = object.userData.occurrenceId
            if (typeof id === 'string') ids.push(id)
        }
        return ids
    }

    dispose() {
        this.meshes.forEach((mesh, i) => {
            mesh.geometry.dispose()
            for (const original of [this.originals[i]].flat()) {
                for (const value of Object.values(original)) {
                    if (value instanceof Texture) value.dispose()
                }
                original.dispose()
            }
        })

        for (const material of this.highlights.values()) material.dispose()
    }

    private highlightOf(material: Material) {
        let highlight = this.highlights.get(material)
        if (!highlight) {
            highlight = material.clone()
            if ('color' in highlight && highlight.color instanceof Color) {
                highlight.color.lerp(HIGHLIGHT, 0.7)
            }
            if ('emissive' in highlight && highlight.emissive instanceof Color) {
                highlight.emissive.copy(HIGHLIGHT).multiplyScalar(0.3)
            }
            this.highlights.set(material, highlight)
        }
        return highlight
    }

    private fillRanges(mask: Uint8Array, ids: string[], value: number) {
        for (const id of ids) {
            const range = this.ranges.get(id)
            if (range) mask.fill(value, ...range)
        }
    }
}
