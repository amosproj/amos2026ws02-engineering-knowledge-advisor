import { useState } from 'react'
import { Alert02Icon, Upload04Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import { cn } from 'cn'

import {
    Alert,
    AlertDescription,
    AlertTitle,
    Button,
    ConfirmationPopup,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
    FieldGroup,
    Progress,
    useAppForm,
} from '@components'
import { formatFileSize } from '@components/atomic/organisms/file-upload/file-validation'

import {
    STEP_FILE_ACCEPT,
    STEP_FILE_MAX_SIZE,
    importMachineSchema,
    type MachineImport,
} from '../models/import-machine-model'
import { useMachineImport, type ActiveImport } from './machine-import-context'

const emptyImport = {
    machineName: '',
    machineDescription: '',
    file: null as File | null,
} as MachineImport

export function ImportMachineDialog() {
    const { activeImport, startImport, cancelImport } = useMachineImport()
    const [open, setOpen] = useState(false)

    const [view, setView] = useState<'form' | 'status'>('form')
    const [submitError, setSubmitError] = useState<string | null>(null)

    const [shownImport, setShownImport] = useState(activeImport)
    if (activeImport && activeImport !== shownImport) setShownImport(activeImport)

    const isOpen = open && (view === 'form' || activeImport !== null)
    const status = view === 'status' ? shownImport : null

    const form = useAppForm({
        defaultValues: emptyImport,
        validators: {
            onSubmit: importMachineSchema,
        },
        onSubmit: async ({ value }) => {
            setSubmitError(null)

            try {
                await startImport(importMachineSchema.parse(value))
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
            open={isOpen}
            onOpenChange={(nextOpen) => {
                if (form.state.isSubmitting) {
                    return
                }

                if (nextOpen) {
                    setView(activeImport ? 'status' : 'form')
                    form.reset()
                    if (activeImport) {
                        form.setFieldValue('machineName', activeImport.name)
                        form.setFieldValue('machineDescription', activeImport.description ?? '')
                        form.setFieldValue('file', activeImport.file)
                    }
                    setSubmitError(null)
                }

                setOpen(nextOpen)
            }}
        >
            <DialogTrigger
                render={
                    <Button
                        variant={activeImport ? 'secondary' : 'default'}
                        className={cn(
                            activeImport && 'relative min-w-36 overflow-hidden',
                            activeImport?.phase === 'processing' &&
                                'hazard-stripes animate-hazard text-hazard-foreground motion-reduce:animate-none',
                        )}
                    />
                }
            >
                {activeImport ? (
                    <ImportProgressLabel activeImport={activeImport} />
                ) : (
                    <>
                        <HugeiconsIcon
                            icon={Upload04Icon}
                            strokeWidth={2}
                            data-icon="inline-start"
                        />
                        Import
                    </>
                )}
            </DialogTrigger>
            <DialogContent className="sm:max-w-xl">
                <DialogHeader>
                    <DialogTitle>
                        {status ? 'Importing machine 3D model' : 'Import machine 3D model'}
                    </DialogTitle>
                    <DialogDescription>
                        {!status
                            ? 'Name the machine and add its STEP file.'
                            : status.phase === 'uploading'
                              ? 'The file is being uploaded. Keep this tab open until it is done.'
                              : 'The file has been uploaded and is being processed.'}
                    </DialogDescription>
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
                                                    disabled={isSubmitting || !!status}
                                                />
                                            )}
                                        </form.AppField>
                                        <form.AppField name="machineDescription">
                                            {(field) => (
                                                <field.TextareaForm
                                                    label="Machine description"
                                                    autoComplete="off"
                                                    disabled={isSubmitting || !!status}
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
                                                    disabled={isSubmitting || !!status}
                                                />
                                            )}
                                        </form.AppField>
                                    </FieldGroup>
                                    {status ? (
                                        <ImportStatus
                                            activeImport={status}
                                            onCancel={cancelImport}
                                            onClose={() => setOpen(false)}
                                        />
                                    ) : (
                                        <>
                                            {submitError ? (
                                                <Alert variant="destructive">
                                                    <HugeiconsIcon
                                                        icon={Alert02Icon}
                                                        strokeWidth={2}
                                                    />
                                                    <AlertTitle>Import failed</AlertTitle>
                                                    <AlertDescription>
                                                        {submitError}
                                                    </AlertDescription>
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
                                </>
                            )}
                        </form.Subscribe>
                    </form.AppForm>
                </form>
            </DialogContent>
        </Dialog>
    )
}

function ImportProgressLabel({ activeImport }: { activeImport: ActiveImport }) {
    if (activeImport.phase === 'processing') {
        return <span className="font-semibold">Processing</span>
    }

    return (
        <>
            <span
                aria-hidden="true"
                className="bg-primary/25 absolute inset-y-0 left-0 transition-[width]"
                style={{ width: `${activeImport.percent}%` }}
            />
            <span className="relative tabular-nums">Uploading {activeImport.percent} %</span>
        </>
    )
}

type ImportStatusProps = {
    activeImport: ActiveImport
    onCancel: () => void
    onClose: () => void
}

function ImportStatus({ activeImport, onCancel, onClose }: ImportStatusProps) {
    const { file, phase, percent } = activeImport
    const isUploading = phase === 'uploading'

    return (
        <>
            {isUploading ? (
                <Progress value={percent} aria-label="Upload progress">
                    <span className="text-muted-foreground text-sm tabular-nums">
                        {formatFileSize((file.size * percent) / 100)} of {formatFileSize(file.size)}{' '}
                        ({percent} %)
                    </span>
                </Progress>
            ) : (
                <div
                    role="progressbar"
                    aria-label="Processing"
                    className="hazard-stripes animate-hazard h-2 rounded-2xl motion-reduce:animate-none"
                />
            )}
            <DialogFooter>
                {isUploading ? (
                    <ConfirmationPopup
                        title="Cancel the import?"
                        description="The upload stops and the machine is not imported."
                        confirmLabel="Cancel import"
                        cancelLabel="Keep uploading"
                        onConfirm={onCancel}
                    >
                        <Button type="button" variant="destructive">
                            Cancel import
                        </Button>
                    </ConfirmationPopup>
                ) : null}
                <Button type="button" variant="outline" onClick={onClose}>
                    Close
                </Button>
            </DialogFooter>
        </>
    )
}
