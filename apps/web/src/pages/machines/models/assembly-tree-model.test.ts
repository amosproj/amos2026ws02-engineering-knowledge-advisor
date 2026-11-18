import { describe, expect, it } from 'vitest'

import type { RecordTree } from '../query/machine-api'
import {
    ancestorIds,
    formatDimensions,
    indexAssembly,
    isHidden,
    occurrencesOf,
    showNode,
    toAssemblyNode,
    visibleRows,
} from './assembly-tree-model'

function instance(
    id: string,
    name: string,
    children: RecordTree[] = [],
    { groupId = `G-${id}`, occurrenceId = `O-${id}` as string | null } = {},
): RecordTree {
    return {
        record: {
            '@id': id,
            '@type': 'AssemblyInstance',
            name,
            instanceOf: groupId,
            properties: occurrenceId ? { occurrenceId } : undefined,
        },
        children,
    }
}

describe('toAssemblyNode', () => {
    it('keeps only instances and sorts them by name naturally', () => {
        const tree = instance('root', 'Cell', [
            instance('b', 'Gripper:10'),
            { record: { '@id': 'k', '@type': 'KnowledgeItem' }, children: [] },
            instance('a', 'Gripper:2', [instance('c', 'Screw:1')]),
        ])

        const node = toAssemblyNode(tree)

        expect(node.children.map((child) => child.name)).toEqual(['Gripper:2', 'Gripper:10'])
        expect(node.children[0].children[0]).toMatchObject({
            id: 'c',
            groupId: 'G-c',
        })
    })
})

describe('indexAssembly', () => {
    it('finds each instance by its own occurrence, even when instances share a group', () => {
        const screw = { groupId: 'G-screw' }
        const index = indexAssembly(
            toAssemblyNode(
                instance('root', 'Cell', [
                    instance('a', 'Frame', [
                        instance('s1', 'Screw:1', [], screw),
                        instance('s2', 'Screw:2', [], screw),
                    ]),
                    instance('b', 'Cover', [], { occurrenceId: null }),
                ]),
            ),
        )

        expect(index.byOccurrence.get('O-s2')?.id).toBe('s2')
        expect(index.byOccurrence.size).toBe(4)
        expect(ancestorIds(index.parentIds, 's2')).toEqual(['a', 'root'])
    })
})

describe('showNode', () => {
    // root > a > b > (c, d), a > e, root > f
    const index = indexAssembly(
        toAssemblyNode(
            instance('root', 'Cell', [
                instance('a', 'A', [
                    instance('b', 'B', [instance('c', 'C'), instance('d', 'D')]),
                    instance('e', 'E'),
                ]),
                instance('f', 'F'),
            ]),
        ),
    )

    it('brings back only the shown branch from below a hidden ancestor', () => {
        const hidden = showNode(index, new Set(['a']), 'c')

        expect([...hidden].sort()).toEqual(['d', 'e'])
        expect(isHidden(hidden, index.parentIds, 'c')).toBe(false)
    })

    it('keeps the hidden parts below the shown one hidden', () => {
        const hidden = showNode(index, new Set(['a', 'c']), 'b')

        expect([...hidden].sort()).toEqual(['c', 'e'])
    })
})

describe('occurrencesOf', () => {
    it('stands for an unmapped node with its nearest mapped descendants', () => {
        const node = toAssemblyNode(
            instance(
                'a',
                'A',
                [
                    instance('b', 'B'),
                    instance('c', 'C', [instance('d', 'D')], { occurrenceId: null }),
                ],
                {
                    occurrenceId: null,
                },
            ),
        )

        expect(occurrencesOf(node).sort()).toEqual(['O-b', 'O-d'])
    })
})

describe('visibleRows', () => {
    it('lists children only below expanded nodes', () => {
        const root = toAssemblyNode(
            instance('root', 'Cell', [
                instance('a', 'Frame', [instance('c', 'Screw')]),
                instance('b', 'Gripper', [instance('d', 'Finger')]),
            ]),
        )

        const rows = visibleRows(root, new Set(['root', 'a']))

        expect(
            rows.map(({ node, parentId, level, position, setSize }) => [
                node.id,
                parentId,
                level,
                `${position}/${setSize}`,
            ]),
        ).toEqual([
            ['root', undefined, 1, '1/1'],
            ['a', 'root', 2, '1/2'],
            ['c', 'a', 3, '1/1'],
            ['b', 'root', 2, '2/2'],
        ])
    })
})

describe('formatDimensions', () => {
    it('converts meters to millimeters', () => {
        const group = {
            '@id': 'g',
            name: 'Frame',
            properties: { sizeX: 1.25, sizeY: 0.0805, sizeZ: 2 },
        }

        expect(formatDimensions(group)).toMatch(/^1.?250 × 80[.,]5 × 2.?000 mm$/)
    })

    it('returns undefined when a size is missing', () => {
        expect(
            formatDimensions({ '@id': 'g', name: 'Frame', properties: { sizeX: 1 } }),
        ).toBeUndefined()
    })
})
