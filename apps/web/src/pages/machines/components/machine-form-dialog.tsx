import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { FieldGroup, toast, useAppForm } from '@components'

import { errorMessage } from '../models/machine-errors'
import { machineFormSchema, orNull, type MachineForm } from '../models/machine-model'
import { createMachine, machinesQueryKey, updateMachine, type Machine } from '../query/machine-api'
import { DialogForm, FormDialog, FormDialogFooter, type FormDialogControls } from './form-dialog'

type MachineFormDialogProps = {
    // Edited machine, a new machine without it
    machine?: Machine
    trigger?: React.ReactElement
    open?: boolean
    onOpenChange?: (open: boolean) => void
    onCreated?: (machine: Machine) => void
}

export function MachineFormDialog({ machine, onCreated, ...dialogProps }: MachineFormDialogProps) {
    return (
        <FormDialog
            title={machine ? 'Edit machine' : 'New machine'}
            description="Only the name is required."
            {...dialogProps}
        >
            {(dialog) => (
                <MachineFormBody machine={machine} onCreated={onCreated} dialog={dialog} />
            )}
        </FormDialog>
    )
}

type MachineFormBodyProps = {
    machine?: Machine
    onCreated?: (machine: Machine) => void
    dialog: FormDialogControls
}

function MachineFormBody({ machine, onCreated, dialog }: MachineFormBodyProps) {
    const [error, setError] = useState<string | null>(null)

    const save = useMutation({
        mutationFn: (value: MachineForm) => {
            const body = {
                name: value.name,
                identifier: orNull(value.identifier),
                customer: orNull(value.customer),
                description: orNull(value.description),
            }
            return machine
                ? updateMachine({ params: { id: machine.id }, body })
                : createMachine({ body })
        },
        meta: { invalidates: [machinesQueryKey] },
    })

    const form = useAppForm({
        defaultValues: toForm(machine),
        validators: { onSubmit: machineFormSchema },
        onSubmit: async ({ value }) => {
            setError(null)
            dialog.setBusy(true)
            try {
                const saved = await save.mutateAsync(machineFormSchema.parse(value))
                dialog.close()
                toast.add({
                    type: 'success',
                    title: machine ? 'Machine saved' : 'Machine created',
                    description: saved.name,
                })
                if (!machine) onCreated?.(saved)
            } catch (saveError) {
                setError(errorMessage(saveError))
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

function toForm(machine: Machine | undefined): MachineForm {
    return {
        name: machine?.name ?? '',
        identifier: machine?.identifier ?? '',
        customer: machine?.customer ?? '',
        description: machine?.description ?? '',
    }
}
