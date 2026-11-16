import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { InformationCircleIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

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
import { StatusBadge } from './status-badge'

export function MachinesTable({ machines }: { machines: MachineView[] | undefined }) {
    return (
        <Table>
            <TableHeader>
                <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Identifier</TableHead>
                    <TableHead>Customer</TableHead>
                    <TableHead>CAD file</TableHead>
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
                    : Array.from({ length: 5 }, (_, index) => (
                          <TableRow key={index}>
                              {Array.from({ length: 6 }, (_, cell) => (
                                  <TableCell key={cell}>
                                      <Skeleton className="h-5 w-full" />
                                  </TableCell>
                              ))}
                          </TableRow>
                      ))}
            </TableBody>
        </Table>
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

    return (
        <TableRow className="has-[a:focus-visible]:ring-ring relative cursor-pointer has-[a:focus-visible]:ring-2">
            <TableCell className="max-w-64">
                <Link
                    to="/machines/$machineId"
                    params={{ machineId }}
                    className="block truncate font-medium outline-none after:absolute after:inset-0"
                >
                    {record.name}
                </Link>
                {record.description ? (
                    <p className="text-muted-foreground truncate">{record.description}</p>
                ) : null}
            </TableCell>
            <TableCell>{record.identifier}</TableCell>
            <TableCell className="max-w-48 truncate">{record.customer}</TableCell>
            <TableCell className="max-w-48 truncate">{cadFile?.name}</TableCell>
            <TableCell>
                {status === 'failed' && cadFile && !importItem ? (
                    <FailedStatus cadFileId={cadFile['@id']} />
                ) : (
                    <StatusBadge status={status} importItem={importItem} />
                )}
            </TableCell>
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
