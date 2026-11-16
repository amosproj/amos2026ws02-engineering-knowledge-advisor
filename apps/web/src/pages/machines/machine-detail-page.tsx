import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from '@tanstack/react-router'
import { Cancel01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import { cn } from 'cn'

import {
    Button,
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
} from '@components'
import { HttpError } from '@queries/query-errors'

import { AssemblyDetails } from './components/assembly-details'
import { AssemblyTree } from './components/assembly-tree'
import { useCadFileImport, type ImportItem } from './components/cad-file-import-context'
import { toAssemblyNode, type AssemblyNode } from './models/assembly-tree-model'
import {
    assemblyTreeQuery,
    machineQuery,
    type MachineDetail,
    type RecordTree,
} from './query/machine-api'

const toTree = (data: RecordTree | null) => (data ? toAssemblyNode(data) : null)

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
    const [selected, setSelected] = useState<AssemblyNode>()
    const isMobile = useIsMobile()
    const { items } = useCadFileImport()
    const importItem = items.find((item) => item.machineId === machineId)

    if (machine.isPending) {
        return <Skeleton className="min-h-96 flex-1 rounded-xl" />
    }
    if (machine.isError) {
        const notFound = machine.error instanceof HttpError && machine.error.status === 404
        return (
            <Empty className="border">
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
    const viewer = (
        <div
            className={cn(
                'bg-muted/50 dark:bg-background text-muted-foreground flex items-center justify-center text-sm',
                isMobile ? 'min-h-48 rounded-xl border' : 'absolute inset-0 border-t',
            )}
        >
            3D view coming soon
        </div>
    )
    const treePanel = (
        <Panel className={isMobile ? 'h-96' : 'h-full'} title="Assembly tree">
            <ScrollArea className="min-h-0 flex-1">
                <div className="p-2">
                    <TreeArea
                        machine={machine.data}
                        importItem={importItem}
                        selectedId={selected?.id}
                        onSelect={setSelected}
                    />
                </div>
            </ScrollArea>
        </Panel>
    )
    const detailsPanel = selected ? (
        <Panel className="max-h-full" title={selected.name} onClose={() => setSelected(undefined)}>
            <div className="min-h-0 flex-1 overflow-auto p-2">
                <AssemblyDetails node={selected} machineName={record.name} />
            </div>
        </Panel>
    ) : null

    if (isMobile) {
        return (
            <div className="flex flex-1 flex-col gap-3">
                {viewer}
                {treePanel}
                {detailsPanel}
            </div>
        )
    }

    return (
        <div className="relative -mx-4 -mb-4 min-h-128 flex-1">
            {viewer}
            <div className="pointer-events-none absolute inset-2">
                <ResizablePanelGroup>
                    <ResizablePanel
                        id="tree"
                        defaultSize={320}
                        minSize={200}
                        maxSize="45%"
                        groupResizeBehavior="preserve-pixel-size"
                    >
                        {treePanel}
                    </ResizablePanel>
                    <PanelHandle label="Resize assembly tree" />
                    <ResizablePanel id="viewer" />
                    {detailsPanel ? (
                        <>
                            <PanelHandle label="Resize details" />
                            <ResizablePanel
                                id="details"
                                defaultSize={288}
                                minSize={200}
                                maxSize="45%"
                                groupResizeBehavior="preserve-pixel-size"
                            >
                                {detailsPanel}
                            </ResizablePanel>
                        </>
                    ) : null}
                </ResizablePanelGroup>
            </div>
        </div>
    )
}

function PanelHandle({ label }: { label: string }) {
    return (
        <ResizableHandle
            aria-label={label}
            className="focus-visible:bg-ring pointer-events-auto mx-0.5 my-3 w-1 rounded-full bg-transparent focus-visible:ring-0"
        />
    )
}

type PanelProps = {
    title: string
    className: string
    onClose?: () => void
    children: React.ReactNode
}

function Panel({ title, className, onClose, children }: PanelProps) {
    return (
        <section
            aria-label={title}
            className={cn(
                'bg-card dark:bg-sidebar pointer-events-auto flex flex-col rounded-xl border shadow-lg',
                className,
            )}
        >
            <header className="flex h-11 shrink-0 items-center justify-between gap-2 border-b px-3">
                <h2 className="truncate text-sm font-medium" title={title}>
                    {title}
                </h2>
                {onClose ? (
                    <Button variant="ghost" size="icon-sm" aria-label="Close" onClick={onClose}>
                        <HugeiconsIcon icon={Cancel01Icon} strokeWidth={2} />
                    </Button>
                ) : null}
            </header>
            {children}
        </section>
    )
}

type TreeAreaProps = {
    machine: MachineDetail
    importItem: ImportItem | undefined
    selectedId: string | undefined
    onSelect: (node: AssemblyNode) => void
}

function TreeArea({ machine, importItem, selectedId, onSelect }: TreeAreaProps) {
    const tree = useQuery({
        ...assemblyTreeQuery(machine.record['@id']),
        enabled: machine.status === 'ready',
        select: toTree,
    })

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
    return <AssemblyTree root={tree.data} selectedId={selectedId} onSelect={onSelect} />
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
