import { useEffect, useState } from 'react'
import { Alert02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

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
} from '@components'
import { SubscribeForm } from '@components/forms/subscribe-form'
import { cn } from 'cn'

export type FormDialogControls = {
    // Closes the dialog, e.g. after a save
    close: () => void
    // Closes the dialog, after asking first if there is unsaved input
    cancel: () => void
    // While busy, the dialog cannot be closed
    setBusy: (busy: boolean) => void
    // Unsaved input: closing asks first, and leaving or reloading the page warns
    setUnsaved: (unsaved: boolean) => void
}

type FormDialogProps = {
    title: string
    description: string
    // Opens the dialog when clicked. Without it, open the dialog with `open`.
    trigger?: React.ReactElement
    open?: boolean
    onOpenChange?: (open: boolean) => void
    // Room for a form laid out in two columns
    wide?: boolean
    // The form, mounted again on each opening so it starts from fresh values
    children: (dialog: FormDialogControls) => React.ReactNode
}

export function FormDialog({
    title,
    description,
    trigger,
    open: controlledOpen,
    onOpenChange,
    wide = false,
    children,
}: FormDialogProps) {
    const [ownOpen, setOwnOpen] = useState(false)
    const [busy, setBusy] = useState(false)
    const [unsaved, setUnsaved] = useState(false)
    const [confirmingDiscard, setConfirmingDiscard] = useState(false)
    const open = controlledOpen ?? ownOpen

    const setOpen = (nextOpen: boolean) => {
        if (!nextOpen) setUnsaved(false)
        setOwnOpen(nextOpen)
        onOpenChange?.(nextOpen)
    }

    const cancel = () => (unsaved ? setConfirmingDiscard(true) : setOpen(false))

    // The browser's own prompt on reload, closing the tab or leaving the app
    useEffect(() => {
        if (!open || !unsaved) return
        const warn = (event: BeforeUnloadEvent) => event.preventDefault()
        window.addEventListener('beforeunload', warn)
        return () => window.removeEventListener('beforeunload', warn)
    }, [open, unsaved])

    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (busy) return
                if (nextOpen) setOpen(true)
                else cancel()
            }}
        >
            {trigger ? <DialogTrigger render={trigger} /> : null}
            <DialogContent
                className={cn(
                    'flex max-h-[calc(100dvh-2rem)] flex-col overflow-hidden',
                    wide ? 'sm:max-w-3xl' : 'sm:max-w-lg',
                )}
            >
                <DialogHeader>
                    <DialogTitle>{title}</DialogTitle>
                    <DialogDescription>{description}</DialogDescription>
                </DialogHeader>

                <div className="-mr-2 min-h-0 overflow-y-auto px-2">
                    {children({ close: () => setOpen(false), cancel, setBusy, setUnsaved })}
                </div>
            </DialogContent>
            <ConfirmationPopup
                open={confirmingDiscard}
                onOpenChange={setConfirmingDiscard}
                title="Discard your changes?"
                description="What you entered is not saved yet."
                confirmLabel="Discard changes"
                cancelLabel="Keep editing"
                onConfirm={() => setOpen(false)}
            />
        </Dialog>
    )
}

type DialogFormProps = {
    onSubmit: () => void
    submitting: boolean
    children: React.ReactNode
}

export function DialogForm({ onSubmit, submitting, children }: DialogFormProps) {
    return (
        <form
            noValidate
            onSubmit={(event) => {
                event.preventDefault()
                onSubmit()
            }}
        >
            {/* Disabled while submitting, so the form cannot be edited or cancelled meanwhile */}
            <fieldset disabled={submitting} className="flex min-w-0 flex-col gap-6">
                {children}
            </fieldset>
        </form>
    )
}

type FormDialogFooterProps = {
    error: string | null
    submitLabel: string
    onCancel: () => void
}

export function FormDialogFooter({ error, submitLabel, onCancel }: FormDialogFooterProps) {
    return (
        <>
            {error ? (
                <Alert variant="destructive">
                    <HugeiconsIcon icon={Alert02Icon} strokeWidth={2} />
                    <AlertTitle>That did not work</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            ) : null}
            <DialogFooter>
                <Button type="button" variant="outline" onClick={onCancel}>
                    Cancel
                </Button>
                <SubscribeForm>{submitLabel}</SubscribeForm>
            </DialogFooter>
        </>
    )
}
