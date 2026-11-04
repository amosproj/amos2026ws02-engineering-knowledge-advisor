import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { FieldGroup, useAppForm } from '@components'

import { errorMessage } from '../models/machine-errors'
import { cadFileFormSchema } from '../models/machine-model'
import { machinesQueryKey, renameCadFile, type CadFile } from '../query/machine-api'
import { DialogForm, FormDialog, FormDialogFooter, type FormDialogControls } from './form-dialog'

type RenameCadFileDialogProps = {
    cadFile: CadFile
    open: boolean
    onOpenChange: (open: boolean) => void
}

export function RenameCadFileDialog({ cadFile, ...dialogProps }: RenameCadFileDialogProps) {
    return (
        <FormDialog
            title="Rename CAD file"
            description="The name is a label, the file itself does not change."
            {...dialogProps}
        >
            {(dialog) => <RenameCadFileBody cadFile={cadFile} dialog={dialog} />}
        </FormDialog>
    )
}

function RenameCadFileBody({ cadFile, dialog }: { cadFile: CadFile; dialog: FormDialogControls }) {
    const [error, setError] = useState<string | null>(null)

    const rename = useMutation({
        mutationFn: (name: string) => renameCadFile({ params: { id: cadFile.id }, body: { name } }),
        meta: { invalidates: [machinesQueryKey] },
    })

    const form = useAppForm({
        defaultValues: { name: cadFile.name },
        validators: { onSubmit: cadFileFormSchema },
        onSubmit: async ({ value }) => {
            setError(null)
            dialog.setBusy(true)
            try {
                await rename.mutateAsync(cadFileFormSchema.parse(value).name)
                dialog.close()
            } catch (renameError) {
                setError(errorMessage(renameError))
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
                        </FieldGroup>
                        <FormDialogFooter
                            error={error}
                            submitLabel="Rename"
                            onCancel={dialog.close}
                        />
                    </DialogForm>
                )}
            </form.Subscribe>
        </form.AppForm>
    )
}
