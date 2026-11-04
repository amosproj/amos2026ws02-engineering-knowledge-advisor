import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { FieldGroup, toast, useAppForm } from '@components'

import { errorMessage } from '../models/machine-errors'
import { assemblyGroupFormSchema, orNull, type AssemblyGroupForm } from '../models/machine-model'
import {
    createAssemblyGroup,
    machinesQueryKey,
    updateAssemblyGroup,
    type AssemblyGroup,
} from '../query/machine-api'
import { DialogForm, FormDialog, FormDialogFooter, type FormDialogControls } from './form-dialog'

type AssemblyGroupFormDialogProps = {
    machineId: string
    // Edited group, a new group without it
    group?: AssemblyGroup
    trigger?: React.ReactElement
    open?: boolean
    onOpenChange?: (open: boolean) => void
}

export function AssemblyGroupFormDialog({
    machineId,
    group,
    ...dialogProps
}: AssemblyGroupFormDialogProps) {
    return (
        <FormDialog
            title={group ? 'Edit assembly group' : 'New assembly group'}
            description="Only the name is required."
            {...dialogProps}
        >
            {(dialog) => (
                <AssemblyGroupFormBody machineId={machineId} group={group} dialog={dialog} />
            )}
        </FormDialog>
    )
}

type AssemblyGroupFormBodyProps = {
    machineId: string
    group?: AssemblyGroup
    dialog: FormDialogControls
}

function AssemblyGroupFormBody({ machineId, group, dialog }: AssemblyGroupFormBodyProps) {
    const [error, setError] = useState<string | null>(null)

    const save = useMutation({
        mutationFn: (value: AssemblyGroupForm) => {
            const body = {
                name: value.name,
                identifier: orNull(value.identifier),
                description: orNull(value.description),
            }
            return group
                ? updateAssemblyGroup({ params: { id: group.id }, body })
                : createAssemblyGroup({ params: { id: machineId }, body })
        },
        meta: { invalidates: [machinesQueryKey] },
    })

    const form = useAppForm({
        defaultValues: toForm(group),
        validators: { onSubmit: assemblyGroupFormSchema },
        onSubmit: async ({ value }) => {
            setError(null)
            dialog.setBusy(true)
            try {
                const saved = await save.mutateAsync(assemblyGroupFormSchema.parse(value))
                dialog.close()
                toast.add({
                    type: 'success',
                    title: group ? 'Assembly group saved' : 'Assembly group added',
                    description: saved.name,
                })
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
                                        description="Assembly group number, e.g. AG-01."
                                        autoComplete="off"
                                    />
                                )}
                            </form.AppField>
                            <form.AppField name="description">
                                {(field) => (
                                    <field.TextareaForm label="Description" autoComplete="off" />
                                )}
                            </form.AppField>
                        </FieldGroup>
                        <FormDialogFooter
                            error={error}
                            submitLabel={group ? 'Save' : 'Add'}
                            onCancel={dialog.close}
                        />
                    </DialogForm>
                )}
            </form.Subscribe>
        </form.AppForm>
    )
}

function toForm(group: AssemblyGroup | undefined): AssemblyGroupForm {
    return {
        name: group?.name ?? '',
        identifier: group?.identifier ?? '',
        description: group?.description ?? '',
    }
}
