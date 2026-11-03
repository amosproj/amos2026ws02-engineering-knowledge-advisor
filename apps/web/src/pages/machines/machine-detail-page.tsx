import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { Add01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Button,
    Card,
    CardContent,
    ConfirmationPopup,
    Empty,
    EmptyContent,
    EmptyDescription,
    EmptyHeader,
    EmptyTitle,
    Skeleton,
    toast,
} from '@components'
import { HttpError } from '@queries/query-errors'

import { ActionsMenu } from './components/actions-menu'
import { AssemblyGroupCard } from './components/assembly-group-card'
import { AssemblyGroupFormDialog } from './components/assembly-group-form-dialog'
import { hasPendingUpload, useCadFileImport } from './components/cad-file-import-context'
import { MachineFormDialog } from './components/machine-form-dialog'
import { StatusBadge } from './components/status-badge'
import { errorMessage } from './models/machine-errors'
import {
    deleteMachine,
    machineQuery,
    machinesQueryKey,
    type MachineDetails,
} from './query/machine-api'

const POLL_MS = 3_000

export function MachineDetailPage() {
    const { machineId } = useParams({ from: '/machines/$machineId' })

    const {
        data: machine,
        error,
        refetch,
    } = useQuery({
        ...machineQuery(machineId),
        refetchOnWindowFocus: true,
        refetchInterval: (query) =>
            !query.state.error && query.state.data && isBusy(query.state.data) ? POLL_MS : false,
    })

    // Also when the machine was loaded before and deleted since
    const notFound = error instanceof HttpError && error._tag === 'NotFound'
    if (!machine || notFound) {
        if (!error) return <Skeleton className="mx-auto mt-10 h-40 w-full max-w-6xl" />
        return (
            <Empty className="mx-auto mt-10 w-full max-w-6xl border">
                <EmptyHeader>
                    <EmptyTitle>
                        {notFound
                            ? 'This machine does not exist'
                            : 'The machine could not be loaded'}
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
                            Back to the machines
                        </Button>
                    ) : (
                        <Button variant="outline" onClick={() => void refetch()}>
                            Try again
                        </Button>
                    )}
                </EmptyContent>
            </Empty>
        )
    }

    return (
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-2 py-6 md:py-10">
            <Link to="/machines" className="text-muted-foreground text-sm hover:underline">
                ← Machines
            </Link>
            <MachineHeader machine={machine} />

            <div className="flex items-center justify-between gap-4">
                <h2 className="font-heading text-lg font-semibold">Assembly groups</h2>
                <AssemblyGroupFormDialog
                    machineId={machine.id}
                    trigger={
                        <Button variant="outline">
                            <HugeiconsIcon
                                icon={Add01Icon}
                                strokeWidth={2}
                                data-icon="inline-start"
                            />
                            Add group
                        </Button>
                    }
                />
            </div>
            {machine.assembly_groups.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                    No assembly groups yet. Add one to import its STEP files.
                </p>
            ) : (
                machine.assembly_groups.map((group) => (
                    <AssemblyGroupCard key={group.id} group={group} />
                ))
            )}
        </div>
    )
}

function MachineHeader({ machine }: { machine: MachineDetails }) {
    const navigate = useNavigate()
    const { items } = useCadFileImport()
    const isUploading = hasPendingUpload(
        items,
        machine.assembly_groups.map((group) => group.id),
    )
    const [editing, setEditing] = useState(false)
    const [deleting, setDeleting] = useState(false)

    const remove = useMutation({
        mutationFn: () => deleteMachine({ params: { id: machine.id } }),
        meta: { invalidates: [machinesQueryKey], invalidateOnError: true },
        onSuccess: () => {
            toast.add({ type: 'success', title: 'Machine deleted', description: machine.name })
            void navigate({ to: '/machines' })
        },
        onError: (error) =>
            toast.add({ type: 'error', title: 'Delete failed', description: errorMessage(error) }),
    })

    return (
        <div className="flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex min-w-0 items-center gap-3">
                    <h1 className="font-heading truncate text-2xl font-semibold tracking-tight">
                        {machine.name}
                    </h1>
                    <StatusBadge status={machine.status} />
                </div>
                <ActionsMenu
                    label={`Actions of ${machine.name}`}
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
                <MachineFormDialog machine={machine} open={editing} onOpenChange={setEditing} />
                <ConfirmationPopup
                    open={deleting}
                    onOpenChange={setDeleting}
                    title="Delete this machine?"
                    description={`${machine.name}, its ${machine.assembly_group_count} assembly groups and ${machine.cad_file_count} CAD files are permanently deleted.`}
                    confirmLabel="Delete machine"
                    cancelLabel="Keep machine"
                    onConfirm={() => remove.mutate()}
                />
            </div>
            <Card>
                <CardContent>
                    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm md:grid-cols-4">
                        <Fact label="Identifier" value={machine.identifier} />
                        <Fact label="Customer" value={machine.customer} />
                        <Fact label="Assembly groups" value={machine.assembly_group_count} />
                        <Fact label="CAD files" value={machine.cad_file_count} />
                        <div className="col-span-full">
                            <Fact label="Description" value={machine.description} multiline />
                        </div>
                    </dl>
                </CardContent>
            </Card>
        </div>
    )
}

type FactProps = {
    label: string
    value: string | number | null
    multiline?: boolean
}

function Fact({ label, value, multiline }: FactProps) {
    return (
        <div className="flex min-w-0 flex-col gap-1">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className={multiline ? 'whitespace-pre-wrap' : 'truncate'}>
                {value === null || value === '' ? (
                    <span className="text-muted-foreground">—</span>
                ) : (
                    value
                )}
            </dd>
        </div>
    )
}

function isBusy(machine: MachineDetails) {
    return machine.assembly_groups.some((group) =>
        group.cad_files.some((file) => file.status === 'uploading' || file.status === 'processing'),
    )
}
