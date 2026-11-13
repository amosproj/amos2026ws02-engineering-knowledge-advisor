import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { FieldGroup, toast, useAppForm } from '@components'

import { errorMessage, isStale } from '../models/machine-errors'
import {
    STEP_FILE_ACCEPT,
    STEP_FILE_MAX_SIZE,
    machineFormSchema,
    orNull,
    type MachineForm,
} from '../models/machine-model'
import {
    createMachine,
    machinesQueryKey,
    updateMachine,
    type MachineView,
} from '../query/machine-api'
import { useCadFileImport } from './cad-file-import-context'
import { DialogForm, FormDialog, FormDialogFooter, type FormDialogControls } from './form-dialog'

type MachineFormDialogProps = {
    // Edited machine, a new machine without it
    machine?: MachineView
    trigger?: React.ReactElement
    open?: boolean
    onOpenChange?: (open: boolean) => void
}

export function MachineFormDialog({ machine, ...dialogProps }: MachineFormDialogProps) {
    return (
        <FormDialog
            title={machine ? 'Edit machine' : 'New machine'}
            description={
                machine
                    ? 'Only the name is required.'
                    : 'Only the name is required. The STEP file uploads in the background, keep this tab open until it is uploaded.'
            }
            scrollable
            {...dialogProps}
        >
            {(dialog) => <MachineFormBody machine={machine} dialog={dialog} />}
        </FormDialog>
    )
}

type MachineFormBodyProps = {
    machine?: MachineView
    dialog: FormDialogControls
}

function MachineFormBody({ machine, dialog }: MachineFormBodyProps) {
    const queryClient = useQueryClient()
    const { startImport } = useCadFileImport()
    const [error, setError] = useState<string | null>(null)
    // Version of the form values: a refetch while editing must not hide a concurrent save
    const [version] = useState(machine?.version)

    const refresh = () => void queryClient.invalidateQueries({ queryKey: machinesQueryKey })

    const save = async (value: MachineForm) => {
        if (machine) {
            await updateMachine({
                params: { id: machine.record['@id'] },
                headers: { 'If-Match': `"${version}"` },
                body: {
                    name: value.name,
                    identifier: orNull(value.identifier),
                    customer: orNull(value.customer),
                    description: orNull(value.description),
                },
            })
            return
        }
        const created = await createMachine({
            body: {
                '@type': 'Machine',
                name: value.name,
                identifier: value.identifier || undefined,
                customer: value.customer || undefined,
                description: value.description || undefined,
            },
        })
        if (!value.file) return
        try {
            await startImport({ machineId: created.id, file: value.file })
        } catch (importError) {
            toast.add({
                type: 'error',
                title: 'The upload did not start',
                description: errorMessage(importError),
                timeout: 0,
            })
        }
    }

    const form = useAppForm({
        defaultValues: toForm(machine),
        validators: { onSubmit: machineFormSchema },
        onSubmit: async ({ value }) => {
            setError(null)
            dialog.setBusy(true)
            try {
                const parsed = machineFormSchema.parse(value)
                await save(parsed)
                refresh()
                dialog.close()
                toast.add({
                    type: 'success',
                    title: machine ? 'Machine saved' : 'Machine created',
                    description: parsed.name,
                })
            } catch (saveError) {
                if (isStale(saveError)) {
                    refresh()
                    setError('Someone changed this machine meanwhile. Close and open it again.')
                } else {
                    setError(errorMessage(saveError))
                }
            } finally {
                dialog.setBusy(false)
            }
        },
    })

    return (
        <form.AppForm>
            <form.Subscribe selector={(state) => state.isSubmitting}>
                {(isSubmitting) => (
                    <DialogForm onSubmit={() => void form.handleSubmit()} submitting={isSubmitting}>
                        <FieldGroup>
                            <form.AppField name="name">
                                {(field) => <field.InputForm label="Name" autoComplete="off" />}
                            </form.AppField>
                            <form.AppField name="identifier">
                                {(field) => (
                                    <field.InputForm
                                        label="Identifier"
                                        description="Project or serial number, e.g. RC-01."
                                        autoComplete="off"
                                    />
                                )}
                            </form.AppField>
                            <form.AppField name="customer">
                                {(field) => <field.InputForm label="Customer" autoComplete="off" />}
                            </form.AppField>
                            <form.AppField name="description">
                                {(field) => (
                                    <field.TextareaForm label="Description" autoComplete="off" />
                                )}
                            </form.AppField>
                            {machine ? null : (
                                <form.AppField name="file">
                                    {(field) => (
                                        <field.FileUploadForm
                                            label="STEP file"
                                            description="Optional, it can also be uploaded later."
                                            mode="single"
                                            accept={STEP_FILE_ACCEPT}
                                            maxSize={STEP_FILE_MAX_SIZE}
                                        />
                                    )}
                                </form.AppField>
                            )}
                        </FieldGroup>
                        <FormDialogFooter
                            error={error}
                            submitLabel={machine ? 'Save' : 'Create'}
                            onCancel={dialog.close}
                        />
                    </DialogForm>
                )}
            </form.Subscribe>
        </form.AppForm>
    )
}

function toForm(machine: MachineView | undefined): MachineForm {
    const record = machine?.record
    return {
        name: record?.name ?? '',
        identifier: record?.identifier ?? '',
        customer: record?.customer ?? '',
        description: record?.description ?? '',
        file: null,
    }
}
