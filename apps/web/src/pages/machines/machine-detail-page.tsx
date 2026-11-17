import { lazy, Suspense, useCallback, useEffect, useEffectEvent, useRef, useState } from 'react'
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { Link, useParams } from '@tanstack/react-router'
import {
    ArrowLeft01Icon,
    Cancel01Icon,
    HierarchyIcon,
    MinusSignIcon,
} from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import { cn } from 'cn'
import { usePanelRef } from 'react-resizable-panels'

import {
    Button,
    Drawer,
    DrawerContent,
    DrawerTitle,
    Empty,
    EmptyContent,
    EmptyDescription,
    EmptyHeader,
    EmptyTitle,
    ResizableHandle,
    ResizablePanel,
    ResizablePanelGroup,
    ScrollArea,
    Skeleton,
    Spinner,
    useIsMobile,
    useSettings,
} from '@components'
import { HttpError } from '@queries/query-errors'

import { AssemblyDetails } from './components/assembly-details'
import { AssemblyTree } from './components/assembly-tree'
import { useCadFileImport, type ImportItem } from './components/cad-file-import-context'
import { ViewerErrorBoundary } from './components/viewer-error-boundary'
import {
    indexAssembly,
    toAssemblyNode,
    type AssemblyIndex,
    type AssemblyNode,
} from './models/assembly-tree-model'
import { findCadFile } from './models/machine-model'
import type { ViewInset } from './models/viewer-camera-model'
import {
    assemblyTreeQuery,
    machineQuery,
    type MachineView as MachineData,
    type RecordTree,
} from './query/machine-api'

const MachineViewer = lazy(() => import('./components/machine-viewer'))

const NO_INSET: ViewInset = { left: 0, right: 0 }

const toTree = (data: RecordTree | null) => (data ? indexAssembly(toAssemblyNode(data)) : null)

export function MachineDetailPage() {
    const { machineId } = useParams({ from: '/machines/$machineId' })
    return <MachineView key={machineId} machineId={machineId} />
}

function MachineView({ machineId }: { machineId: string }) {
    const machine = useQuery({
        ...machineQuery(machineId),
        refetchInterval: (query) => {
            const status = query.state.data?.status
            return status === 'uploading' || status === 'processing' ? 3_000 : false
        },
    })
    const tree = useQuery({
        ...assemblyTreeQuery(machineId),
        enabled: machine.data?.status === 'ready',
        select: toTree,
    })
    const [selected, setSelected] = useState<AssemblyNode>()
    // Incremented by a selection in the tree, for the 3D view to frame the part
    const [focusRequest, setFocusRequest] = useState(0)
    // Incremented by a pick in the 3D view, for the tree to show the part
    const [revealRequest, setRevealRequest] = useState(0)
    const { settings } = useSettings()
    const isMobile = useIsMobile()
    const { items } = useCadFileImport()
    const importItem = items.find((item) => item.machineId === machineId)
    const containerRef = useRef<HTMLDivElement>(null)
    const [inset, setInset] = useState(NO_INSET)
    const treePanelRef = usePanelRef()
    const detailsPanelRef = usePanelRef()
    const [treeCollapsed, setTreeCollapsed] = useState(false)
    const treeButtonRef = useRef<HTMLButtonElement>(null)
    const collapseButtonRef = useRef<HTMLButtonElement>(null)
    const [drawer, setDrawer] = useState<'tree' | 'details' | null>(null)
    const drawerTitleRef = useRef<HTMLHeadingElement>(null)

    if (!isMobile && drawer !== null) setDrawer(null)

    // Set by the buttons that hide themselves; focus moves once the new layout is committed
    const focusPending = useRef(false)

    useEffect(() => {
        if (!focusPending.current) return
        focusPending.current = false
        const frame = requestAnimationFrame(() =>
            (treeCollapsed ? treeButtonRef : collapseButtonRef).current?.focus(),
        )
        return () => cancelAnimationFrame(frame)
    }, [treeCollapsed])

    useEffect(() => {
        if (drawer !== null) {
            drawerTitleRef.current?.focus()
        } else if (focusPending.current) {
            focusPending.current = false
            treeButtonRef.current?.focus()
        }
    }, [drawer, selected])

    // The 3D view spans the whole area; the free space between the floating panels is measured here
    const visibleRef = useCallback((element: HTMLDivElement | null) => {
        if (!element) return
        const observer = new ResizeObserver(() => {
            const container = containerRef.current
            if (!container) return
            const visible = element.getBoundingClientRect()
            const bounds = container.getBoundingClientRect()
            setInset({ left: visible.left - bounds.left, right: bounds.right - visible.right })
        })
        observer.observe(element)
        return () => observer.disconnect()
    }, [])

    const deselect = () => {
        setSelected(undefined)
        detailsPanelRef.current?.collapse()
        if (drawer === 'details') setDrawer(null)
    }

    const onEscape = useEffectEvent((event: KeyboardEvent) => {
        if (event.key !== 'Escape' || event.defaultPrevented || isMobile || !selected) return
        // Open dialogs and menus close on Escape themselves
        if (document.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"]')) return
        deselect()
    })

    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => onEscape(event)
        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [])

    if (machine.isPending) {
        return <Skeleton className="m-4 mt-0 min-h-96 flex-1 rounded-xl" />
    }
    if (machine.isError) {
        const notFound = machine.error instanceof HttpError && machine.error.status === 404
        return (
            <Empty className="m-4 mt-0 border">
                <EmptyHeader>
                    <EmptyTitle>
                        {notFound ? 'Machine not found' : 'The machine could not be loaded'}
                    </EmptyTitle>
                    <EmptyDescription>
                        {notFound
                            ? 'It may have been deleted.'
                            : 'Check your connection and try again.'}
                    </EmptyDescription>
                </EmptyHeader>
                <EmptyContent>
                    {notFound ? (
                        <Button
                            variant="outline"
                            nativeButton={false}
                            render={<Link to="/machines" />}
                        >
                            Back to machines
                        </Button>
                    ) : (
                        <Button variant="outline" onClick={() => void machine.refetch()}>
                            Try again
                        </Button>
                    )}
                </EmptyContent>
            </Empty>
        )
    }

    const { record } = machine.data
    const showDetails = (node: AssemblyNode) => {
        setSelected(node)
        if (isMobile) setDrawer('details')
        else if (detailsPanelRef.current?.isCollapsed()) detailsPanelRef.current.resize(288)
    }
    const selectInTree = (node: AssemblyNode) => {
        showDetails(node)
        if (settings.focusOnSelect) setFocusRequest((count) => count + 1)
    }
    const pickInView = (occurrenceIds: string[]) => {
        const node = occurrenceIds
            .map((id) => tree.data?.byOccurrence.get(id))
            .find((found) => found !== undefined)
        if (!node) return
        showDetails(node)
        setRevealRequest((count) => count + 1)
        if (!isMobile && treePanelRef.current?.isCollapsed()) treePanelRef.current.expand()
    }
    const closeDetails = () => {
        setSelected(undefined)
        detailsPanelRef.current?.collapse()
    }
    const treeArea = (
        <TreeArea
            machine={machine.data}
            tree={tree}
            importItem={importItem}
            selectedId={selected?.id}
            revealRequest={revealRequest}
            visible={isMobile ? drawer === 'tree' : !treeCollapsed}
            onSelect={selectInTree}
        />
    )
    const details = selected ? <AssemblyDetails node={selected} machineName={record.name} /> : null

    const collapseTree = () => {
        focusPending.current = true
        treePanelRef.current?.collapse()
    }
    const expandTree = () => {
        focusPending.current = true
        treePanelRef.current?.expand()
    }
    const closeDrawer = () => {
        focusPending.current = true
        setDrawer(null)
    }

    return (
        <div ref={containerRef} className="relative flex-1 overflow-hidden">
            <div className="absolute inset-0 border-t bg-linear-to-b from-neutral-100 to-neutral-300 dark:from-neutral-700 dark:to-neutral-900">
                <ViewerArea
                    machine={machine.data}
                    inset={isMobile ? NO_INSET : inset}
                    selected={selected?.occurrenceId}
                    focusRequest={focusRequest}
                    onPick={pickInView}
                    onMiss={deselect}
                />
            </div>
            {isMobile ? (
                <>
                    {drawer === null ? (
                        <TreeButton ref={treeButtonRef} onClick={() => setDrawer('tree')} />
                    ) : null}
                    <Drawer
                        open={drawer !== null}
                        onOpenChange={(open) => {
                            if (!open) closeDrawer()
                        }}
                        modal={false}
                        disablePointerDismissal
                        showSwipeHandle
                        snapPoints={[0.45, 1]}
                    >
                        <DrawerContent keepMounted>
                            <header className="flex h-11 shrink-0 items-center gap-1 border-b px-2">
                                {drawer === 'details' ? (
                                    <Button
                                        variant="ghost"
                                        size="icon-sm"
                                        aria-label="Back to the assembly tree"
                                        onClick={() => setDrawer('tree')}
                                    >
                                        <HugeiconsIcon icon={ArrowLeft01Icon} strokeWidth={2} />
                                    </Button>
                                ) : null}
                                <DrawerTitle
                                    ref={drawerTitleRef}
                                    tabIndex={-1}
                                    className="min-w-0 flex-1 truncate px-1 text-sm outline-none"
                                >
                                    {drawer === 'details' && selected
                                        ? selected.name
                                        : 'Assembly tree'}
                                </DrawerTitle>
                                <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    aria-label="Close"
                                    onClick={closeDrawer}
                                >
                                    <HugeiconsIcon icon={Cancel01Icon} strokeWidth={2} />
                                </Button>
                            </header>
                            <div className="min-h-0 flex-1 overflow-y-auto p-2 pb-[calc(var(--drawer-snap-point-offset,0px)+0.5rem)]">
                                <div hidden={drawer === 'details'}>{treeArea}</div>
                                {drawer === 'details' ? details : null}
                            </div>
                        </DrawerContent>
                    </Drawer>
                </>
            ) : (
                <div className="pointer-events-none absolute inset-0 top-px">
                    <ResizablePanelGroup>
                        <ResizablePanel
                            id="tree"
                            panelRef={treePanelRef}
                            collapsible
                            collapsedSize={0}
                            defaultSize={320}
                            minSize={200}
                            maxSize="45%"
                            groupResizeBehavior="preserve-pixel-size"
                            onResize={(size) => setTreeCollapsed(size.inPixels === 0)}
                        >
                            <Panel
                                className={cn(
                                    'h-full border-r shadow-lg',
                                    treeCollapsed && 'invisible',
                                )}
                                title="Assembly tree"
                                action={
                                    <Button
                                        ref={collapseButtonRef}
                                        variant="ghost"
                                        size="icon-sm"
                                        aria-label="Collapse the assembly tree"
                                        onClick={collapseTree}
                                    >
                                        <HugeiconsIcon icon={MinusSignIcon} strokeWidth={2} />
                                    </Button>
                                }
                            >
                                <ScrollArea className="min-h-0 flex-1">
                                    <div className="p-2">{treeArea}</div>
                                </ScrollArea>
                            </Panel>
                        </ResizablePanel>
                        <PanelHandle label="Resize assembly tree" />
                        <ResizablePanel id="viewer">
                            <div ref={visibleRef} className="h-full" />
                        </ResizablePanel>
                        <PanelHandle label="Resize details" disabled={!selected} />
                        <ResizablePanel
                            id="details"
                            panelRef={detailsPanelRef}
                            collapsible
                            collapsedSize={0}
                            defaultSize={0}
                            minSize={200}
                            maxSize="45%"
                            groupResizeBehavior="preserve-pixel-size"
                            onResize={(size) => {
                                if (size.inPixels === 0) setSelected(undefined)
                            }}
                        >
                            {selected ? (
                                <div className="h-full py-2 pr-2">
                                    <Panel
                                        className="max-h-full rounded-xl border"
                                        title={selected.name}
                                        action={
                                            <Button
                                                variant="ghost"
                                                size="icon-sm"
                                                aria-label="Close"
                                                onClick={closeDetails}
                                            >
                                                <HugeiconsIcon
                                                    icon={Cancel01Icon}
                                                    strokeWidth={2}
                                                />
                                            </Button>
                                        }
                                    >
                                        <div className="min-h-0 flex-1 overflow-auto p-2">
                                            {details}
                                        </div>
                                    </Panel>
                                </div>
                            ) : null}
                        </ResizablePanel>
                    </ResizablePanelGroup>
                    {treeCollapsed ? <TreeButton ref={treeButtonRef} onClick={expandTree} /> : null}
                </div>
            )}
        </div>
    )
}

function TreeButton({ ref, onClick }: { ref: React.Ref<HTMLButtonElement>; onClick: () => void }) {
    return (
        <Button
            ref={ref}
            variant="outline"
            size="icon"
            aria-label="Show the assembly tree"
            className="pointer-events-auto absolute top-3 left-3 rounded-full shadow-md"
            onClick={onClick}
        >
            <HugeiconsIcon icon={HierarchyIcon} strokeWidth={2} />
        </Button>
    )
}

type ViewerAreaProps = {
    machine: MachineData
    inset: ViewInset
    selected: string | undefined
    focusRequest: number
    onPick: (occurrenceIds: string[]) => void
    onMiss: () => void
}

function ViewerArea({ machine, inset, ...selection }: ViewerAreaProps) {
    const cadFile = findCadFile(machine)
    if (machine.status !== 'ready' || !cadFile) {
        return (
            <ViewerMessage inset={inset}>
                The 3D view appears once a CAD file is imported.
            </ViewerMessage>
        )
    }
    return (
        <ViewerErrorBoundary
            fallback={
                <ViewerMessage inset={inset}>The 3D view could not be displayed.</ViewerMessage>
            }
        >
            <Suspense
                fallback={
                    <ViewerMessage inset={inset}>
                        <Spinner />
                    </ViewerMessage>
                }
            >
                <MachineViewer fileId={cadFile['@id']} inset={inset} {...selection} />
            </Suspense>
        </ViewerErrorBoundary>
    )
}

function ViewerMessage({ inset, children }: { inset: ViewInset; children: React.ReactNode }) {
    return (
        <div
            className="text-muted-foreground absolute inset-y-0 flex items-center justify-center text-sm"
            style={{ left: inset.left, right: inset.right }}
        >
            {children}
        </div>
    )
}

function PanelHandle({ label, disabled }: { label: string; disabled?: boolean }) {
    return (
        <ResizableHandle
            aria-label={label}
            disabled={disabled}
            className="focus-visible:bg-ring pointer-events-auto mx-0.5 my-3 w-1 rounded-full bg-transparent focus-visible:ring-0"
        />
    )
}

type PanelProps = {
    title: string
    className: string
    action: React.ReactNode
    children: React.ReactNode
}

function Panel({ title, className, action, children }: PanelProps) {
    return (
        <section
            aria-label={title}
            className={cn('bg-card dark:bg-sidebar pointer-events-auto flex flex-col', className)}
        >
            <header className="flex h-11 shrink-0 items-center justify-between gap-2 border-b px-3">
                <h2 className="truncate text-sm font-medium" title={title}>
                    {title}
                </h2>
                {action}
            </header>
            {children}
        </section>
    )
}

type TreeAreaProps = {
    machine: MachineData
    tree: UseQueryResult<AssemblyIndex | null>
    importItem: ImportItem | undefined
    selectedId: string | undefined
    revealRequest: number
    visible: boolean
    onSelect: (node: AssemblyNode) => void
}

function TreeArea({ machine, tree, importItem, ...treeProps }: TreeAreaProps) {
    switch (machine.status) {
        case 'empty':
            return <Message title="No CAD file">Import a STEP file from the machine list.</Message>
        case 'uploading':
            return importItem ? (
                <Message title="Uploading the CAD file" busy />
            ) : (
                <Message title="Upload interrupted">
                    Import the STEP file again from the machine list.
                </Message>
            )
        case 'processing':
            return <Message title="Importing the assembly tree" busy />
        case 'failed':
            return (
                <Message title="Import failed">
                    See the machine list for the reason and retry.
                </Message>
            )
    }

    if (tree.isPending) {
        return (
            <div className="grid gap-2 p-1">
                {Array.from({ length: 6 }, (_, index) => (
                    <Skeleton key={index} className="h-5" style={{ width: `${90 - index * 8}%` }} />
                ))}
            </div>
        )
    }
    if (tree.isError) {
        return (
            <Message title="The assembly tree could not be loaded">
                <Button
                    variant="outline"
                    size="sm"
                    className="mt-2"
                    onClick={() => void tree.refetch()}
                >
                    Try again
                </Button>
            </Message>
        )
    }
    if (!tree.data) {
        return <Message title="No assembly tree">The CAD file contains no assembly.</Message>
    }
    return <AssemblyTree tree={tree.data} {...treeProps} />
}

function Message({
    title,
    busy,
    children,
}: {
    title: string
    busy?: boolean
    children?: React.ReactNode
}) {
    return (
        <div className="flex flex-col items-center gap-1 px-4 py-10 text-center text-sm">
            {busy ? <Spinner className="mb-2" /> : null}
            <p className="font-medium">{title}</p>
            {children ? <div className="text-muted-foreground">{children}</div> : null}
        </div>
    )
}
