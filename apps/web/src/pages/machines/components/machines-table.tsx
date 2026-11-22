import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { InformationCircleIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import { cn } from 'cn'

import {
    ConfirmationPopup,
    Skeleton,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
    toast,
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from '@components'

import { cadFileErrorMessage, errorMessage } from '../models/machine-errors'
import { findCadFile } from '../models/machine-model'
import {
    cadFileQuery,
    deleteRecord,
    machinesQueryKey,
    type MachineView,
} from '../query/machine-api'
import { ActionsMenu, type Action } from './actions-menu'
import { useCadFileImport } from './cad-file-import-context'
import { cadFileActionLabels, toCadFileAction, type CadFileAction } from './cad-file-action'
import { CadFileDialog } from './cad-file-dialog'
import { MachineFormDialog } from './machine-form-dialog'
import { MachinePreview } from './machine-preview'
import { StatusBadge } from './status-badge'

// Below these container widths, the name cell shows the essentials of the hidden columns(for responsive)
const WIDE_COLUMN = 'hidden @3xl:table-cell'
const WIDEST_COLUMN = 'hidden @5xl:table-cell'

export function MachinesTable({ machines }: { machines: MachineView[] | undefined }) {
    return (
        <div className="@container">
            <Table>
                <TableHeader className="hidden @3xl:table-header-group">
                    <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Identifier</TableHead>
                        <TableHead>Customer</TableHead>
                        <TableHead className={WIDEST_COLUMN}>CAD file</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="w-10">
                            <span className="sr-only">Actions</span>
                        </TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {machines
                        ? machines.map((machine) => (
                              <MachineRow key={machine.record['@id']} machine={machine} />
                          ))
                        : Array.from({ length: 5 }, (_, index) => <SkeletonRow key={index} />)}
                </TableBody>
            </Table>
        </div>
    )
}

function SkeletonRow() {
    return (
        <TableRow>
            <TableCell className="w-full py-3">
                <div className="flex items-center gap-3 @3xl:gap-4">
                    <Skeleton className="aspect-4/3 w-24 shrink-0 rounded-lg @3xl:w-28" />
                    <Skeleton className="h-5 w-full max-w-48" />
                </div>
            </TableCell>
            {[WIDE_COLUMN, WIDE_COLUMN, WIDEST_COLUMN, WIDE_COLUMN].map((column, index) => (
                <TableCell key={index} className={column}>
                    <Skeleton className="h-5 w-20" />
                </TableCell>
            ))}
            <TableCell />
        </TableRow>
    )
}

function MachineRow({ machine }: { machine: MachineView }) {
    const { record, status } = machine
    const machineId = record['@id']
    const cadFile = findCadFile(machine)
    const { items } = useCadFileImport()
    const importItem = items.find((item) => item.machineId === machineId)
    const [editing, setEditing] = useState(false)
    const [deleting, setDeleting] = useState(false)
    const [cadFileAction, setCadFileAction] = useState<CadFileAction | null>(null)

    const remove = useMutation({
        mutationFn: () => deleteRecord({ params: { id: machineId } }),
        meta: { invalidates: [machinesQueryKey], invalidateOnError: true },
        onSuccess: () =>
            toast.add({ type: 'success', title: 'Machine deleted', description: record.name }),
        onError: (error) =>
            toast.add({ type: 'error', title: 'Delete failed', description: errorMessage(error) }),
    })

    const actions: Action[] = [{ label: 'Edit', onSelect: () => setEditing(true) }]
    const fileAction = importItem ? null : toCadFileAction(status, cadFile)
    if (fileAction) {
        actions.push({
            label: cadFileActionLabels[fileAction.kind],
            onSelect: () => setCadFileAction(fileAction),
        })
    }
    actions.push({
        label: importItem ? 'Delete (upload running)' : 'Delete',
        onSelect: () => setDeleting(true),
        destructive: true,
        disabled: remove.isPending || importItem !== undefined,
    })

    const statusBadge =
        status === 'failed' && cadFile && !importItem ? (
            <FailedStatus cadFileId={cadFile['@id']} />
        ) : (
            <StatusBadge status={status} importItem={importItem} />
        )

    return (
        <TableRow className="has-[a:focus-visible]:ring-ring relative cursor-pointer has-[a:focus-visible]:ring-2">
            <TableCell className="w-full max-w-0 py-3">
                <div className="flex items-center gap-3 @3xl:gap-4">
                    <MachinePreview
                        key={cadFile?.['@id']}
                        cadFileId={status === 'ready' ? cadFile?.['@id'] : undefined}
                    />
                    <div className="min-w-0">
                        <Link
                            to="/machines/$machineId"
                            params={{ machineId }}
                            className="block truncate text-base font-medium outline-none after:absolute after:inset-0"
                        >
                            {record.name}
                        </Link>
                        <p className="truncate @3xl:hidden">
                            {[record.identifier, record.customer].filter(Boolean).join(' · ')}
                        </p>
                        {record.description ? (
                            <p className="text-muted-foreground mt-0.5 line-clamp-1 whitespace-normal @3xl:line-clamp-2">
                                {record.description}
                            </p>
                        ) : null}
                        <div className="mt-1 @3xl:hidden">{statusBadge}</div>
                    </div>
                </div>
            </TableCell>
            <TableCell className={cn(WIDE_COLUMN, 'max-w-40 truncate')}>
                {record.identifier}
            </TableCell>
            <TableCell className={cn(WIDE_COLUMN, 'max-w-48 truncate')}>
                {record.customer}
            </TableCell>
            <TableCell className={cn(WIDEST_COLUMN, 'max-w-48 truncate')}>
                {cadFile?.name}
            </TableCell>
            <TableCell className={WIDE_COLUMN}>{statusBadge}</TableCell>
            <TableCell className="relative z-10 text-right">
                <ActionsMenu label={`Actions of ${record.name}`} size="icon-sm" actions={actions} />
                <MachineFormDialog machine={machine} open={editing} onOpenChange={setEditing} />
                {cadFileAction ? (
                    <CadFileDialog
                        machineId={machineId}
                        action={cadFileAction}
                        open
                        onOpenChange={(open) => !open && setCadFileAction(null)}
                    />
                ) : null}
                <ConfirmationPopup
                    open={deleting}
                    onOpenChange={setDeleting}
                    title="Delete this machine?"
                    description={`${record.name}, its CAD file and its assembly groups are permanently deleted. Knowledge items about it are kept for review.`}
                    confirmLabel="Delete machine"
                    cancelLabel="Keep machine"
                    onConfirm={() => remove.mutate()}
                />
            </TableCell>
        </TableRow>
    )
}

function FailedStatus({ cadFileId }: { cadFileId: string }) {
    const { data } = useQuery(cadFileQuery(cadFileId))
    const reason = cadFileErrorMessage(data?.upload?.errorCode)
    return (
        <Tooltip>
            <TooltipTrigger
                render={
                    <button
                        type="button"
                        aria-label={`Failed: ${reason}`}
                        className="focus-visible:ring-ring relative z-10 rounded-2xl outline-none focus-visible:ring-2"
                    />
                }
            >
                <StatusBadge status="failed">
                    <HugeiconsIcon
                        icon={InformationCircleIcon}
                        strokeWidth={2}
                        data-icon="inline-end"
                    />
                </StatusBadge>
            </TooltipTrigger>
            <TooltipContent>{reason}</TooltipContent>
        </Tooltip>
    )
}
