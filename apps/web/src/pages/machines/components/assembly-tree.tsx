import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import { cn } from 'cn'

import {
    ancestorIds,
    visibleRows,
    type AssemblyIndex,
    type AssemblyNode,
    type TreeRow,
} from '../models/assembly-tree-model'

type AssemblyTreeProps = {
    tree: AssemblyIndex
    selectedId: string | undefined
    /** Incremented when a part picked in the 3D view must be shown in the tree. */
    revealRequest: number
    /** False while the tree is collapsed or behind the details. */
    visible: boolean
    onSelect: (node: AssemblyNode) => void
}

export function AssemblyTree({
    tree,
    selectedId,
    revealRequest,
    visible,
    onSelect,
}: AssemblyTreeProps) {
    const { root, parentIds } = tree
    const treeRef = useRef<HTMLDivElement>(null)
    const [expandedIds, setExpandedIds] = useState(() => new Set([root.id]))
    const [focusedId, setFocusedId] = useState(root.id)
    const [revealed, setRevealed] = useState(revealRequest)

    // A part picked in the 3D view may sit below collapsed nodes
    if (revealRequest !== revealed) {
        setRevealed(revealRequest)
        if (selectedId) {
            const hidden = ancestorIds(parentIds, selectedId).filter((id) => !expandedIds.has(id))
            if (hidden.length > 0) setExpandedIds(new Set([...expandedIds, ...hidden]))
            setFocusedId(selectedId)
        }
    }

    useEffect(() => {
        if (!visible || !selectedId) return
        treeRef.current
            ?.querySelector(`[data-id="${CSS.escape(selectedId)}"]`)
            ?.scrollIntoView({ block: 'nearest' })
    }, [selectedId, revealRequest, visible])
    const rows = useMemo(() => visibleRows(root, expandedIds), [root, expandedIds])
    const tabStopId = rows.some((row) => row.node.id === focusedId) ? focusedId : root.id

    const setExpanded = (id: string, expanded: boolean) =>
        setExpandedIds((previous) => {
            const next = new Set(previous)
            if (expanded) next.add(id)
            else next.delete(id)
            return next
        })

    const focusRow = (row: TreeRow | undefined) => {
        if (!row) return
        setFocusedId(row.node.id)
        treeRef.current
            ?.querySelector<HTMLElement>(`[data-id="${CSS.escape(row.node.id)}"]`)
            ?.focus()
    }

    const onKeyDown = (event: React.KeyboardEvent, index: number) => {
        const { node, parentId } = rows[index]
        const expanded = expandedIds.has(node.id)
        switch (event.key) {
            case 'ArrowDown':
                focusRow(rows[index + 1])
                break
            case 'ArrowUp':
                focusRow(rows[index - 1])
                break
            case 'Home':
                focusRow(rows[0])
                break
            case 'End':
                focusRow(rows.at(-1))
                break
            case 'ArrowRight':
                if (node.children.length === 0) return
                if (expanded) focusRow(rows[index + 1])
                else setExpanded(node.id, true)
                break
            case 'ArrowLeft':
                if (expanded) setExpanded(node.id, false)
                else focusRow(rows.find((row) => row.node.id === parentId))
                break
            case 'Enter':
            case ' ':
                onSelect(node)
                break
            default:
                return
        }
        event.preventDefault()
    }

    return (
        <div ref={treeRef} role="tree" aria-label="Assembly tree" className="text-sm">
            {rows.map(({ node, level, position, setSize }, index) => {
                const hasChildren = node.children.length > 0
                const expanded = expandedIds.has(node.id)
                const selected = node.id === selectedId
                return (
                    <div
                        key={node.id}
                        role="treeitem"
                        data-id={node.id}
                        aria-level={level}
                        aria-posinset={position}
                        aria-setsize={setSize}
                        aria-expanded={hasChildren ? expanded : undefined}
                        aria-selected={selected}
                        tabIndex={node.id === tabStopId ? 0 : -1}
                        className={cn(
                            'hover:bg-foreground/5 focus-visible:ring-ring flex h-7 cursor-pointer items-center gap-1 rounded-md pr-2 outline-none focus-visible:ring-2',
                            selected && 'bg-foreground/10 hover:bg-foreground/10',
                        )}
                        style={{ paddingLeft: `${(level - 1) * 0.75}rem` }}
                        onKeyDown={(event) => onKeyDown(event, index)}
                        onClick={() => {
                            setFocusedId(node.id)
                            onSelect(node)
                        }}
                    >
                        {hasChildren ? (
                            <span
                                aria-hidden
                                className="text-muted-foreground hover:text-foreground flex size-5 shrink-0 items-center justify-center rounded"
                                onClick={(event) => {
                                    event.stopPropagation()
                                    setFocusedId(node.id)
                                    setExpanded(node.id, !expanded)
                                }}
                            >
                                <HugeiconsIcon
                                    icon={ArrowRight01Icon}
                                    strokeWidth={2}
                                    className={cn(
                                        'size-4 transition-transform',
                                        expanded && 'rotate-90',
                                    )}
                                />
                            </span>
                        ) : (
                            <span className="size-5 shrink-0" />
                        )}
                        <span className="truncate" title={node.name}>
                            {node.name}
                        </span>
                        {hasChildren ? (
                            <span className="text-muted-foreground shrink-0 tabular-nums">
                                ({node.children.length})
                            </span>
                        ) : null}
                    </div>
                )
            })}
        </div>
    )
}
