import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import {
    Button,
    Card,
    CardAction,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
    ConfirmationPopup,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
    toast,
} from '@components'
import { formatFileSize } from '@components/atomic/organisms/file-upload/file-validation'

import { cadFileErrorMessage, errorMessage } from '../models/machine-errors'
import {
    deleteAssemblyGroup,
    deleteCadFile,
    machinesQueryKey,
    type AssemblyGroup,
    type CadFile,
} from '../query/machine-api'
import { ActionsMenu } from './actions-menu'
import { AssemblyGroupFormDialog } from './assembly-group-form-dialog'
import { hasPendingUpload, isCancellable, useCadFileImport } from './cad-file-import-context'
import { formatDateTime } from './format-date-time'
import { ImportCadFilesDialog } from './import-cad-files-dialog'
import { RenameCadFileDialog } from './rename-cad-file-dialog'
import { StatusBadge } from './status-badge'

export function AssemblyGroupCard({ group }: { group: AssemblyGroup }) {
    const { items } = useCadFileImport()
    // Deleting the group now would let a file still uploading from this tab land later
    const isUploading = hasPendingUpload(items, [group.id])
    const [editing, setEditing] = useState(false)
    const [deleting, setDeleting] = useState(false)

    const remove = useMutation({
        mutationFn: () => deleteAssemblyGroup({ params: { id: group.id } }),
        meta: { invalidates: [machinesQueryKey], invalidateOnError: true },
        onSuccess: () =>
            toast.add({
                type: 'success',
                title: 'Assembly group deleted',
                description: group.name,
            }),
        onError: (error) =>
            toast.add({ type: 'error', title: 'Delete failed', description: errorMessage(error) }),
    })

    return (
        <Card>
            <CardHeader>
                <CardTitle>
                    {group.name}
                    {group.identifier ? (
                        <span className="text-muted-foreground ml-2 font-normal">
                            {group.identifier}
                        </span>
                    ) : null}
                </CardTitle>
                {group.description ? <CardDescription>{group.description}</CardDescription> : null}
                <CardAction className="flex items-center gap-2">
                    <ImportCadFilesDialog
                        assemblyGroupId={group.id}
                        trigger={<Button size="sm">Import STEP files</Button>}
                    />
                    <ActionsMenu
                        label={`Actions of ${group.name}`}
                        actions={[
                            { label: 'Edit', onSelect: () => setEditing(true) },
                            {
                                label: isUploading ? 'Delete (uploads running)' : 'Delete',
                                onSelect: () => setDeleting(true),
                                destructive: true,
                                disabled: remove.isPending || isUploading,
                            },
                        ]}
                    />
                </CardAction>
            </CardHeader>
            <CardContent>
                {group.cad_files.length === 0 ? (
                    <p className="text-muted-foreground text-sm">No CAD files yet.</p>
                ) : (
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>File</TableHead>
                                <TableHead>Status</TableHead>
                                <TableHead>Imported</TableHead>
                                <TableHead className="w-10">
                                    <span className="sr-only">Actions</span>
                                </TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {group.cad_files.map((cadFile) => (
                                <CadFileRow key={cadFile.id} cadFile={cadFile} />
                            ))}
                        </TableBody>
                    </Table>
                )}
            </CardContent>

            <AssemblyGroupFormDialog
                machineId={group.machine_id}
                group={group}
                open={editing}
                onOpenChange={setEditing}
            />
            <ConfirmationPopup
                open={deleting}
                onOpenChange={setDeleting}
                title="Delete this assembly group?"
                description={`${group.name} and its ${group.cad_files.length} CAD files are permanently deleted.`}
                confirmLabel="Delete group"
                cancelLabel="Keep group"
                onConfirm={() => remove.mutate()}
            />
        </Card>
    )
}

function CadFileRow({ cadFile }: { cadFile: CadFile }) {
    const { items, cancelImport } = useCadFileImport()
    const importItem = items.find((item) => item.cadFileId === cadFile.id)
    // The upload runs in this tab: stopping it also deletes the file
    const canCancel = importItem !== undefined && isCancellable(importItem)
    const [renaming, setRenaming] = useState(false)
    const [deleting, setDeleting] = useState(false)

    const remove = useMutation({
        mutationFn: () => deleteCadFile({ params: { id: cadFile.id } }),
        meta: { invalidates: [machinesQueryKey], invalidateOnError: true },
        onError: (error) =>
            toast.add({ type: 'error', title: 'Delete failed', description: errorMessage(error) }),
    })

    return (
        <TableRow>
            <TableCell className="max-w-64">
                <p className="truncate font-medium">{cadFile.name}</p>
                <p className="text-muted-foreground">{formatFileSize(cadFile.size_bytes)}</p>
            </TableCell>
            <TableCell className="max-w-64 whitespace-normal">
                <StatusBadge status={cadFile.status} importItem={importItem} />
                {cadFile.status === 'failed' ? (
                    <p className="text-destructive mt-1 text-sm">
                        {cadFileErrorMessage(cadFile.error_code)}
                    </p>
                ) : null}
            </TableCell>
            <TableCell className="text-muted-foreground">
                {formatDateTime(cadFile.created_at)}
            </TableCell>
            <TableCell className="text-right">
                <ActionsMenu
                    label={`Actions of ${cadFile.name}`}
                    size="icon-sm"
                    actions={[
                        { label: 'Rename', onSelect: () => setRenaming(true) },
                        {
                            label: canCancel ? 'Cancel upload' : 'Delete',
                            onSelect: () => setDeleting(true),
                            destructive: true,
                            disabled: remove.isPending,
                        },
                    ]}
                />
                <RenameCadFileDialog cadFile={cadFile} open={renaming} onOpenChange={setRenaming} />
                <ConfirmationPopup
                    open={deleting}
                    onOpenChange={setDeleting}
                    title={canCancel ? 'Cancel this upload?' : 'Delete this CAD file?'}
                    description={
                        canCancel
                            ? `The upload of ${cadFile.name} stops and the file is removed.`
                            : `${cadFile.name} is permanently deleted.`
                    }
                    confirmLabel={canCancel ? 'Cancel upload' : 'Delete file'}
                    cancelLabel={canCancel ? 'Keep uploading' : 'Keep file'}
                    onConfirm={() => (canCancel ? cancelImport(cadFile.id) : remove.mutate())}
                />
            </TableCell>
        </TableRow>
    )
}
