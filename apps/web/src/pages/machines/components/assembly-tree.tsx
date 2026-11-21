import { useEffect, useMemo, useRef, useState } from 'react'
import {
    ArrowRight01Icon,
    MoreHorizontalIcon,
    ViewIcon,
    ViewOffSlashIcon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import { cn } from 'cn'

import {
    Button,
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@components'

import {
    ancestorIds,
    isWithin,
    visibleRows,
    type AssemblyIndex,
    type AssemblyNode,
    type TreeRow,
} from '../models/assembly-tree-model'

export type TreeAction =
    'hide' | 'show' | 'showAll' | 'isolate' | 'exitIsolation' | 'zoom' | 'selectParent'

type HiddenState = 'self' | 'inherited' | undefined

type AssemblyTreeProps = {
    tree: AssemblyIndex
    selectedId: string | undefined
    revealRequest: number
    visible: boolean
    hidden: ReadonlySet<string>
    isolatedId: string | undefined
    onSelect: (node: AssemblyNode) => void
    onAction: (node: AssemblyNode, action: TreeAction) => void
}

export function AssemblyTree({
    tree,
    selectedId,
    revealRequest,
    visible,
    hidden,
    isolatedId,
    onSelect,
    onAction,
}: AssemblyTreeProps) {
    const { root, parentIds, inModel } = tree
    const treeRef = useRef<HTMLDivElement>(null)
    const [expandedIds, setExpandedIds] = useState(() => new Set([root.id]))
    const [focusedId, setFocusedId] = useState(root.id)
    const [revealed, setRevealed] = useState(revealRequest)
    const [menuId, setMenuId] = useState<string>()

    // Row focused when the menu closes, the parent after "Select parent"
    const menuFocusId = useRef<string>(undefined)

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

    const openMenu = (node: AssemblyNode) => {
        setFocusedId(node.id)
        menuFocusId.current = node.id
        setMenuId(node.id)
    }

    const runAction = (node: AssemblyNode, action: TreeAction) => {
        if (action === 'selectParent') {
            const parentId = parentIds.get(node.id)
            if (parentId) {
                menuFocusId.current = parentId
                setFocusedId(parentId)
            }
        }
        onAction(node, action)
    }

    const rowElement = (id: string | undefined) =>
        id
            ? (treeRef.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(id)}"]`) ?? null)
            : null

    // Rows come after their parent, so each one inherits the state computed for it
    const hiddenStates = new Map<string, HiddenState>()
    for (const { node, parentId } of rows) {
        const inherited = parentId !== undefined && hiddenStates.get(parentId) !== undefined
        hiddenStates.set(
            node.id,
            hidden.has(node.id) ? 'self' : inherited ? 'inherited' : undefined,
        )
    }

    const toggleHidden = (node: AssemblyNode) =>
        onAction(node, hiddenStates.get(node.id) ? 'show' : 'hide')

    const onKeyDown = (event: React.KeyboardEvent, index: number) => {
        if (event.target !== event.currentTarget) return
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
            case 'ContextMenu':
                openMenu(node)
                break
            case 'F10':
                if (!event.shiftKey) return
                openMenu(node)
                break
            case 'h':
            case 'H':
                if (event.repeat || event.ctrlKey || event.altKey || event.metaKey) return
                if (!inModel.has(node.id)) return
                toggleHidden(node)
                break
            default:
                return
        }
        event.preventDefault()
    }

    return (
        <div ref={treeRef} role="tree" aria-label="Assembly tree" className="text-sm">
            {rows.map(({ node, parentId, level, position, setSize }, index) => {
                const hasChildren = node.children.length > 0
                const expanded = expandedIds.has(node.id)
                const selected = node.id === selectedId
                const hiddenState = hiddenStates.get(node.id)
                const isRoot = parentId === undefined
                const isolatedOut =
                    isolatedId !== undefined && !isWithin(parentIds, node.id, isolatedId)
                const nodeInModel = inModel.has(node.id)
                return (
                    <div
                        key={node.id}
                        role="treeitem"
                        aria-label={node.name}
                        data-id={node.id}
                        aria-level={level}
                        aria-posinset={position}
                        aria-setsize={setSize}
                        aria-expanded={hasChildren ? expanded : undefined}
                        aria-selected={selected}
                        aria-keyshortcuts={nodeInModel ? 'Shift+F10 H' : 'Shift+F10'}
                        tabIndex={node.id === tabStopId ? 0 : -1}
                        className={cn(
                            'group hover:bg-foreground/5 focus-visible:ring-ring flex h-7 cursor-pointer items-center gap-1 pr-0.5 outline-none focus-visible:ring-2 focus-visible:ring-inset',
                            index % 2 === 1 && 'bg-foreground/[0.03]',
                            selected && 'bg-foreground/10 hover:bg-foreground/10',
                            hiddenState && 'text-muted-foreground',
                            isolatedOut && 'opacity-40',
                        )}
                        style={{ paddingLeft: `${(level - 1) * 0.75}rem` }}
                        onKeyDown={(event) => onKeyDown(event, index)}
                        onContextMenu={(event) => {
                            if (!event.currentTarget.contains(event.target as Node)) return
                            event.preventDefault()
                            openMenu(node)
                        }}
                        onClick={(event) => {
                            const target = event.target as Element
                            // Clicks in the menu, rendered in a portal, bubble through the row too
                            if (!event.currentTarget.contains(target)) return
                            if (target.closest('[data-row-menu]')) return
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
                        <span
                            className={cn('truncate', hiddenState === 'self' && 'line-through')}
                            title={node.name}
                        >
                            {node.name}
                        </span>
                        <div className="ml-auto flex shrink-0 items-center">
                            {nodeInModel ? (
                                <Button
                                    variant="ghost"
                                    size="icon-xs"
                                    tabIndex={-1}
                                    aria-label={`${hiddenState ? 'Show' : 'Hide'} ${node.name}`}
                                    title={`${hiddenState ? 'Show' : 'Hide'} ${node.name}`}
                                    className={cn(
                                        hiddenState === undefined &&
                                            'opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 pointer-coarse:opacity-100',
                                        hiddenState === 'inherited' &&
                                            'opacity-50 hover:opacity-100',
                                    )}
                                    onClick={(event) => {
                                        event.stopPropagation()
                                        focusRow(rows[index])
                                        toggleHidden(node)
                                    }}
                                >
                                    <HugeiconsIcon
                                        icon={hiddenState ? ViewOffSlashIcon : ViewIcon}
                                        strokeWidth={2}
                                    />
                                </Button>
                            ) : (
                                <span className="size-6" />
                            )}
                            <RowMenu
                                node={node}
                                open={menuId === node.id}
                                hiddenState={hiddenState}
                                inModel={nodeInModel}
                                isolated={node.id === isolatedId}
                                canShowAll={hidden.size > 0}
                                isRoot={isRoot}
                                onOpenChange={(open) => {
                                    if (open) openMenu(node)
                                    else setMenuId(undefined)
                                }}
                                onAction={(action) => runAction(node, action)}
                                finalFocus={() => rowElement(menuFocusId.current)}
                            />
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

type RowMenuProps = {
    node: AssemblyNode
    open: boolean
    hiddenState: HiddenState
    inModel: boolean
    isolated: boolean
    canShowAll: boolean
    isRoot: boolean
    onOpenChange: (open: boolean) => void
    onAction: (action: TreeAction) => void
    finalFocus: () => HTMLElement | null
}

function RowMenu({
    node,
    open,
    hiddenState,
    inModel,
    isolated,
    canShowAll,
    isRoot,
    onOpenChange,
    onAction,
    finalFocus,
}: RowMenuProps) {
    const items: { action: TreeAction; label: string; disabled?: boolean }[] = [
        isolated
            ? { action: 'exitIsolation', label: 'Exit isolation' }
            : {
                  action: 'isolate',
                  label: 'Isolate',
                  disabled: !inModel || hiddenState !== undefined,
              },
        { action: 'zoom', label: 'Zoom to', disabled: !inModel || hiddenState !== undefined },
        { action: 'selectParent', label: 'Select parent', disabled: isRoot },
    ]

    return (
        <DropdownMenu open={open} onOpenChange={onOpenChange}>
            <DropdownMenuTrigger
                data-row-menu
                tabIndex={-1}
                aria-label={`Actions of ${node.name}`}
                className="opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 data-popup-open:opacity-100 pointer-coarse:opacity-100"
                render={<Button variant="ghost" size="icon-xs" />}
            >
                <HugeiconsIcon icon={MoreHorizontalIcon} strokeWidth={2} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-40" finalFocus={finalFocus}>
                {items.map((item) => (
                    <DropdownMenuItem
                        key={item.action}
                        disabled={item.disabled}
                        onClick={() => onAction(item.action)}
                    >
                        {item.label}
                    </DropdownMenuItem>
                ))}
                {canShowAll ? (
                    <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => onAction('showAll')}>
                            Show all
                        </DropdownMenuItem>
                    </>
                ) : null}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
