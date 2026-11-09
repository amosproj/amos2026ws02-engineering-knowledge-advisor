import { useState } from 'react'

import { FieldGroup, useAppForm } from '@components'

import { errorMessage } from '../models/machine-errors'
import {
    STEP_FILE_ACCEPT,
    STEP_FILE_MAX_SIZE,
    cadFileFormSchema,
    type CadFileForm,
} from '../models/machine-model'
import { cadFileActionLabels, type CadFileAction } from './cad-file-action'
import { useCadFileImport, type ImportTarget } from './cad-file-import-context'
import { DialogForm, FormDialog, FormDialogFooter, type FormDialogControls } from './form-dialog'

const BACKGROUND_NOTE =
    'The file uploads in the background, keep this tab open until it is uploaded.'

const noFile: CadFileForm = { file: null }

type CadFileDialogProps = {
    machineId: string
    action: CadFileAction
    open: boolean
    onOpenChange: (open: boolean) => void
}

export function CadFileDialog({ machineId, action, ...dialogProps }: CadFileDialogProps) {
    return (
        <FormDialog
            title={cadFileActionLabels[action.kind]}
            description={describe(action)}
            {...dialogProps}
        >
            {(dialog) => <CadFileBody target={toTarget(machineId, action)} dialog={dialog} />}
        </FormDialog>
    )
}

function describe(action: CadFileAction) {
    if (action.kind === 'replace') {
        return `${action.name} is deleted and replaced by the new file. ${BACKGROUND_NOTE}`
    }
    if (action.kind === 'retry' && action.interrupted) {
        return `An upload of this file may still run in another tab, this one replaces it. ${BACKGROUND_NOTE}`
    }
    return BACKGROUND_NOTE
}

function toTarget(machineId: string, action: CadFileAction): Omit<ImportTarget, 'file'> {
    if (action.kind === 'retry') return { machineId, reuseId: action.cadFileId }
    if (action.kind === 'replace') return { machineId, replaceId: action.cadFileId }
    return { machineId }
}

type CadFileBodyProps = {
    target: Omit<ImportTarget, 'file'>
    dialog: FormDialogControls
}

function CadFileBody({ target, dialog }: CadFileBodyProps) {
    const { startImport } = useCadFileImport()
    const [error, setError] = useState<string | null>(null)

    const form = useAppForm({
        defaultValues: noFile,
        validators: { onSubmit: cadFileFormSchema },
        onSubmit: async ({ value }) => {
            const { file } = cadFileFormSchema.parse(value)
            if (!file) return
            setError(null)
            dialog.setBusy(true)
            try {
                await startImport({ ...target, file })
                dialog.close()
            } catch (startError) {
                setError(errorMessage(startError))
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
                            <form.AppField name="file">
                                {(field) => (
                                    <field.FileUploadForm
                                        label="STEP file"
                                        mode="single"
                                        accept={STEP_FILE_ACCEPT}
                                        maxSize={STEP_FILE_MAX_SIZE}
                                    />
                                )}
                            </form.AppField>
                        </FieldGroup>
                        <FormDialogFooter
                            error={error}
                            submitLabel="Upload"
                            onCancel={dialog.close}
                        />
                    </DialogForm>
                )}
            </form.Subscribe>
        </form.AppForm>
    )
}
