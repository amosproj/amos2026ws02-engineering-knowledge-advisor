import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Alert02Icon, InformationCircleIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Alert,
    AlertDescription,
    AlertTitle,
    Button,
    ConfirmationPopup,
    FieldGroup,
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
    toast,
    useAppForm,
} from '@components'
import { formatFileSize } from '@components/atomic/organisms/file-upload/file-validation'

import { machineDetailsSchema, type MachineDetails } from '../models/import-machine-model'
import { machineErrorMessage } from '../models/machine-errors'
import {
    deleteMachine,
    machinesQueryKey,
    updateMachine,
    type Machine,
    type MachineStatus,
} from '../query/machine-api'
import { formatDateTime } from './format-date-time'
import { useMachineImport } from './machine-import-context'
import { MachineStatusBadge } from './machine-status-badge'

type MachineDrawerProps = {
    machine: Machine | undefined
    open: boolean
    onClose: () => void
}

export function MachineDrawer({ machine, open, onClose }: MachineDrawerProps) {
    const { activeImport } = useMachineImport()
    const ownImport = machine && activeImport?.machineId === machine.id ? activeImport : null

    const status = ownImport?.phase ?? machine?.status

    return (
        <Sheet open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
            <SheetContent className="gap-0 data-[side=right]:w-full data-[side=right]:sm:max-w-xl">
                {machine && status ? (
                    <>
                        <SheetHeader className="pr-14">
                            <div className="flex min-w-0 items-center gap-3">
                                <SheetTitle className="truncate text-lg">{machine.name}</SheetTitle>
                                <MachineStatusBadge
                                    status={machine.status}
                                    activeImport={ownImport}
                                />
                            </div>
                            <SheetDescription>
                                Imported {formatDateTime(machine.created_at)}
                            </SheetDescription>
                        </SheetHeader>
                        <div className="flex flex-1 flex-col gap-8 overflow-y-auto px-6 pb-6">
                            <MachineFacts machine={machine} status={status} />
                            <MachineEditForm
                                key={machine.id}
                                machine={machine}
                                disabled={status === 'processing'}
                            />
                            <MachineDangerZone
                                machine={machine}
                                status={status}
                                isOwnImport={!!ownImport}
                            />
                        </div>
                    </>
                ) : null}
            </SheetContent>
        </Sheet>
    )
}

function MachineFacts({ machine, status }: { machine: Machine; status: MachineStatus }) {
    return (
        <section className="flex flex-col gap-4">
            <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
                <dt className="text-muted-foreground">File</dt>
                <dd className="truncate">{machine.original_filename}</dd>
                <dt className="text-muted-foreground">Size</dt>
                <dd>{formatFileSize(machine.size_bytes)}</dd>
                <dt className="text-muted-foreground">Last updated</dt>
                <dd>{formatDateTime(machine.updated_at)}</dd>
            </dl>
            {status === 'failed' ? (
                <Alert variant="destructive">
                    <HugeiconsIcon icon={Alert02Icon} strokeWidth={2} />
                    <AlertTitle>Import failed</AlertTitle>
                    <AlertDescription>{machineErrorMessage(machine.error_code)}</AlertDescription>
                </Alert>
            ) : null}
            {status === 'processing' ? (
                <Alert>
                    <HugeiconsIcon icon={InformationCircleIcon} strokeWidth={2} />
                    <AlertTitle>The STEP file is being verified</AlertTitle>
                    <AlertDescription>
                        Editing and deleting are available once it is done.
                    </AlertDescription>
                </Alert>
            ) : null}
        </section>
    )
}

function toDetails(machine: Machine): MachineDetails {
    return { machineName: machine.name, machineDescription: machine.description ?? '' }
}

function MachineEditForm({ machine, disabled }: { machine: Machine; disabled: boolean }) {
    const [saved, setSaved] = useState(() => toDetails(machine))
    const [submitError, setSubmitError] = useState<string | null>(null)

    const update = useMutation({
        mutationFn: (details: MachineDetails) =>
            updateMachine({
                params: { id: machine.id },
                body: {
                    name: details.machineName,
                    description: details.machineDescription ?? '',
                },
            }),
        meta: { invalidates: [machinesQueryKey], invalidateOnError: true },
    })

    const form = useAppForm({
        defaultValues: saved,
        validators: { onSubmit: machineDetailsSchema },
        onSubmit: async ({ value }) => {
            setSubmitError(null)
            try {
                const updated = await update.mutateAsync(machineDetailsSchema.parse(value))
                // Both, or useAppForm would restore the previous defaults on the next render
                setSaved(toDetails(updated))
                form.reset(toDetails(updated))
                toast.add({ type: 'success', title: 'Machine saved' })
            } catch (error) {
                setSubmitError(
                    error instanceof Error ? error.message : 'The machine could not be saved.',
                )
            }
        },
    })

    return (
        <section className="flex flex-col gap-4">
            <h3 className="font-heading font-medium">Details</h3>
            <form
                noValidate
                className="flex flex-col gap-6"
                onSubmit={(event) => {
                    event.preventDefault()
                    void form.handleSubmit()
                }}
            >
                <form.AppForm>
                    <form.Subscribe selector={(state) => state.isSubmitting}>
                        {(isSubmitting) => (
                            <FieldGroup>
                                <form.AppField name="machineName">
                                    {(field) => (
                                        <field.InputForm
                                            label="Machine name"
                                            autoComplete="off"
                                            disabled={disabled || isSubmitting}
                                        />
                                    )}
                                </form.AppField>
                                <form.AppField name="machineDescription">
                                    {(field) => (
                                        <field.TextareaForm
                                            label="Machine description"
                                            autoComplete="off"
                                            disabled={disabled || isSubmitting}
                                        />
                                    )}
                                </form.AppField>
                            </FieldGroup>
                        )}
                    </form.Subscribe>
                    {submitError ? (
                        <Alert variant="destructive">
                            <HugeiconsIcon icon={Alert02Icon} strokeWidth={2} />
                            <AlertTitle>Save failed</AlertTitle>
                            <AlertDescription>{submitError}</AlertDescription>
                        </Alert>
                    ) : null}
                    <form.Subscribe
                        selector={(state) =>
                            state.values.machineName.trim() !== saved.machineName ||
                            (state.values.machineDescription ?? '').trim() !==
                                saved.machineDescription
                        }
                    >
                        {(isChanged) => (
                            <form.SubscribeForm
                                className="self-end"
                                disabled={disabled || !isChanged}
                            >
                                Save
                            </form.SubscribeForm>
                        )}
                    </form.Subscribe>
                </form.AppForm>
            </form>
        </section>
    )
}

type MachineDangerZoneProps = {
    machine: Machine
    status: MachineStatus
    isOwnImport: boolean
}

function MachineDangerZone({ machine, status, isOwnImport }: MachineDangerZoneProps) {
    const { cancelImport } = useMachineImport()
    const isUploading = status === 'uploading'

    const remove = useMutation({
        mutationFn: () => deleteMachine({ params: { id: machine.id } }),
        // The page closes the drawer once the refreshed list no longer has the machine
        meta: { invalidates: [machinesQueryKey], invalidateOnError: true },
        onSuccess: () =>
            toast.add({
                type: 'success',
                title: isUploading ? 'Import cancelled' : 'Machine deleted',
                description: machine.name,
            }),
        onError: (error) =>
            toast.add({
                type: 'error',
                title: isUploading ? 'Cancel failed' : 'Delete failed',
                description: error.message,
            }),
    })

    const confirm = () => (isOwnImport ? cancelImport() : remove.mutate())

    return (
        <section className="border-destructive/30 mt-auto flex flex-col gap-3 rounded-xl border p-4">
            <div>
                <h3 className="font-heading font-medium">
                    {isUploading ? 'Cancel the import' : 'Delete the machine'}
                </h3>
                <p className="text-muted-foreground text-sm">
                    {isUploading
                        ? 'The upload stops and the machine is removed.'
                        : 'The machine and its STEP file are permanently deleted.'}
                </p>
            </div>
            <ConfirmationPopup
                title={isUploading ? 'Cancel the import?' : 'Delete this machine?'}
                description={
                    isUploading
                        ? 'The upload stops and the machine is not imported.'
                        : `${machine.name} and its STEP file are permanently deleted.`
                }
                confirmLabel={isUploading ? 'Cancel import' : 'Delete machine'}
                cancelLabel={isUploading ? 'Keep uploading' : 'Keep machine'}
                onConfirm={confirm}
            >
                <Button
                    type="button"
                    variant="destructive"
                    className="self-start"
                    disabled={status === 'processing' || remove.isPending}
                >
                    {isUploading ? 'Cancel import' : 'Delete machine'}
                </Button>
            </ConfirmationPopup>
        </section>
    )
}
