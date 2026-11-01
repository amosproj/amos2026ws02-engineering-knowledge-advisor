import { useState } from 'react'
import { Alert02Icon, Upload04Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import { useAppForm } from '../../../forms'
import { Button } from '../../atoms'
import {
    Alert,
    AlertDescription,
    AlertTitle,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
    FieldGroup,
} from '../../molecules'
import {
    STEP_FILE_ACCEPT,
    STEP_FILE_MAX_SIZE,
    importMachineSchema,
    type ImportMachineValues,
    type MachineImport,
} from './import-machine-model'

type ImportMachineDialogProps = {
    onSubmit: (machineImport: MachineImport) => Promise<void>
}

export function ImportMachineDialog({ onSubmit }: ImportMachineDialogProps) {
    const [open, setOpen] = useState(false)
    const [submitError, setSubmitError] = useState<string | null>(null)

    const form = useAppForm({
        defaultValues: {
            machineName: '',
            file: null,
        } as ImportMachineValues,
        validators: {
            onSubmit: importMachineSchema,
        },
        onSubmit: async ({ value }) => {
            setSubmitError(null)

            try {
                await onSubmit(importMachineSchema.parse(value))
                setOpen(false)
            } catch (error) {
                setSubmitError(
                    error instanceof Error
                        ? error.message
                        : 'The import could not be started. Please try again.',
                )
            }
        },
    })

    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (form.state.isSubmitting) {
                    return
                }

                if (nextOpen) {
                    form.reset()
                    setSubmitError(null)
                }

                setOpen(nextOpen)
            }}
        >
            <DialogTrigger render={<Button />}>
                <HugeiconsIcon icon={Upload04Icon} strokeWidth={2} data-icon="inline-start" />
                Import
            </DialogTrigger>
            <DialogContent className="sm:max-w-xl">
                <DialogHeader>
                    <DialogTitle>Import machine 3D model</DialogTitle>
                    <DialogDescription>Name the machine and add its STEP file.</DialogDescription>
                </DialogHeader>
                <form
                    noValidate
                    className="flex min-w-0 flex-col gap-6"
                    onSubmit={(event) => {
                        event.preventDefault()
                        void form.handleSubmit()
                    }}
                >
                    <form.AppForm>
                        <form.Subscribe selector={(state) => state.isSubmitting}>
                            {(isSubmitting) => (
                                <>
                                    <FieldGroup>
                                        <form.AppField name="machineName">
                                            {(field) => (
                                                <field.InputForm
                                                    label="Machine name"
                                                    autoComplete="off"
                                                    disabled={isSubmitting}
                                                />
                                            )}
                                        </form.AppField>
                                        <form.AppField name="file">
                                            {(field) => (
                                                <field.FileUploadForm
                                                    label="STEP file"
                                                    mode="single"
                                                    accept={STEP_FILE_ACCEPT}
                                                    maxSize={STEP_FILE_MAX_SIZE}
                                                    disabled={isSubmitting}
                                                />
                                            )}
                                        </form.AppField>
                                    </FieldGroup>
                                    {submitError ? (
                                        <Alert variant="destructive">
                                            <HugeiconsIcon icon={Alert02Icon} strokeWidth={2} />
                                            <AlertTitle>Import failed</AlertTitle>
                                            <AlertDescription>{submitError}</AlertDescription>
                                        </Alert>
                                    ) : null}
                                    <DialogFooter>
                                        <Button
                                            type="button"
                                            variant="outline"
                                            disabled={isSubmitting}
                                            onClick={() => setOpen(false)}
                                        >
                                            Cancel
                                        </Button>
                                        <form.SubscribeForm>Import</form.SubscribeForm>
                                    </DialogFooter>
                                </>
                            )}
                        </form.Subscribe>
                    </form.AppForm>
                </form>
            </DialogContent>
        </Dialog>
    )
}
