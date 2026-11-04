import { useState } from 'react'

import { FieldGroup, useAppForm } from '@components'

import { errorMessage } from '../models/machine-errors'
import {
    MAX_FILES_PER_IMPORT,
    STEP_FILE_ACCEPT,
    STEP_FILE_MAX_SIZE,
    importCadFilesSchema,
    type ImportCadFiles,
} from '../models/machine-model'
import { useCadFileImport } from './cad-file-import-context'
import { DialogForm, FormDialog, FormDialogFooter, type FormDialogControls } from './form-dialog'

const noFiles: ImportCadFiles = { files: [] }

type ImportCadFilesDialogProps = {
    assemblyGroupId: string
    trigger: React.ReactElement
}

export function ImportCadFilesDialog({ assemblyGroupId, trigger }: ImportCadFilesDialogProps) {
    return (
        <FormDialog
            title="Import STEP files"
            description="The files upload in the background, you can keep working meanwhile. Keep this tab open until they are uploaded."
            trigger={trigger}
        >
            {(dialog) => <ImportCadFilesBody assemblyGroupId={assemblyGroupId} dialog={dialog} />}
        </FormDialog>
    )
}

type ImportCadFilesBodyProps = {
    assemblyGroupId: string
    dialog: FormDialogControls
}

function ImportCadFilesBody({ assemblyGroupId, dialog }: ImportCadFilesBodyProps) {
    const { startImport } = useCadFileImport()
    const [error, setError] = useState<string | null>(null)

    const form = useAppForm({
        defaultValues: noFiles,
        validators: { onSubmit: importCadFilesSchema },
        onSubmit: async ({ value }) => {
            setError(null)
            dialog.setBusy(true)
            try {
                await startImport(assemblyGroupId, importCadFilesSchema.parse(value).files)
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
                            <form.AppField name="files">
                                {(field) => (
                                    <field.FileUploadForm
                                        label="STEP files"
                                        mode="multiple"
                                        maxFiles={MAX_FILES_PER_IMPORT}
                                        accept={STEP_FILE_ACCEPT}
                                        maxSize={STEP_FILE_MAX_SIZE}
                                    />
                                )}
                            </form.AppField>
                        </FieldGroup>
                        <FormDialogFooter
                            error={error}
                            submitLabel="Import"
                            onCancel={dialog.close}
                        />
                    </DialogForm>
                )}
            </form.Subscribe>
        </form.AppForm>
    )
}
