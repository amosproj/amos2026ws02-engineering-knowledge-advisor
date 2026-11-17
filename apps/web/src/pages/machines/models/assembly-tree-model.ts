import type { AssemblyGroup, RecordTree } from '../query/machine-api'

export type AssemblyNode = {
    id: string
    name: string
    groupId: string | undefined
    /** Matches ``userData.occurrenceId`` of the node in the 3D model. */
    occurrenceId: string | undefined
    children: AssemblyNode[]
}

const byName = new Intl.Collator(undefined, { numeric: true }).compare

/** Keeps only assembly instances, sorted by name: the API sorts children by id. */
export function toAssemblyNode({ record, children }: RecordTree): AssemblyNode {
    return {
        id: record['@id'],
        name: record.name ?? record['@id'],
        groupId: record.instanceOf,
        occurrenceId: record.properties?.occurrenceId,
        children: children
            .filter((child) => child.record['@type'] === 'AssemblyInstance')
            .map(toAssemblyNode)
            .sort((a, b) => byName(a.name, b.name)),
    }
}

export type AssemblyIndex = {
    root: AssemblyNode
    byOccurrence: ReadonlyMap<string, AssemblyNode>
    parentIds: ReadonlyMap<string, string>
}

export function indexAssembly(root: AssemblyNode): AssemblyIndex {
    const byOccurrence = new Map<string, AssemblyNode>()
    const parentIds = new Map<string, string>()
    const visit = (node: AssemblyNode) => {
        if (node.occurrenceId) byOccurrence.set(node.occurrenceId, node)
        for (const child of node.children) {
            parentIds.set(child.id, node.id)
            visit(child)
        }
    }
    visit(root)
    return { root, byOccurrence, parentIds }
}

/** Ids of the nodes above ``id``, nearest first. */
export function ancestorIds(parentIds: ReadonlyMap<string, string>, id: string) {
    const ids: string[] = []
    for (let parent = parentIds.get(id); parent; parent = parentIds.get(parent)) ids.push(parent)
    return ids
}

const millimeters = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 })

/** Group sizes are stored in meters. */
export function formatDimensions(group: AssemblyGroup) {
    const { sizeX, sizeY, sizeZ } = group.properties ?? {}
    if (sizeX === undefined || sizeY === undefined || sizeZ === undefined) return undefined
    return `${[sizeX, sizeY, sizeZ].map((size) => millimeters.format(size * 1000)).join(' × ')} mm`
}

export type TreeRow = {
    node: AssemblyNode
    parentId: string | undefined
    level: number
    position: number
    setSize: number
}

/** The rows of the tree in display order, children only below expanded nodes. */
export function visibleRows(root: AssemblyNode, expandedIds: ReadonlySet<string>) {
    const rows: TreeRow[] = []
    const add = (nodes: AssemblyNode[], parentId: string | undefined, level: number) =>
        nodes.forEach((node, index) => {
            rows.push({ node, parentId, level, position: index + 1, setSize: nodes.length })
            if (expandedIds.has(node.id)) add(node.children, node.id, level + 1)
        })
    add([root], undefined, 1)
    return rows
}
