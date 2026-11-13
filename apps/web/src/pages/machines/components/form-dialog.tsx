import { useState } from 'react'
import { Alert02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Alert,
    AlertDescription,
    AlertTitle,
    Button,
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@components'
import { SubscribeForm } from '@components/forms/subscribe-form'

export type FormDialogControls = {
    close: () => void
    // While busy, the dialog cannot be closed
    setBusy: (busy: boolean) => void
}

type FormDialogProps = {
    title: string
    description: string
    // Opens the dialog when clicked. Without it, open the dialog with `open`.
    trigger?: React.ReactElement
    open?: boolean
    onOpenChange?: (open: boolean) => void
    scrollable?: boolean
    // The form, mounted again on each opening so it starts from fresh values
    children: (dialog: FormDialogControls) => React.ReactNode
}

export function FormDialog({
    title,
    description,
    trigger,
    open: controlledOpen,
    onOpenChange,
    scrollable = false,
    children,
}: FormDialogProps) {
    const [ownOpen, setOwnOpen] = useState(false)
    const [busy, setBusy] = useState(false)
    const open = controlledOpen ?? ownOpen

    const setOpen = (nextOpen: boolean) => {
        setOwnOpen(nextOpen)
        onOpenChange?.(nextOpen)
    }

    return (
        <Dialog open={open} onOpenChange={(nextOpen) => !busy && setOpen(nextOpen)}>
            {trigger ? <DialogTrigger render={trigger} /> : null}
            <DialogContent className="sm:max-w-lg max-h-[calc(100dvh-2rem)] flex flex-col overflow-hidden">
                <DialogHeader>
                    <DialogTitle>
                        {title}
                    </DialogTitle>
                    <DialogDescription>{description}</DialogDescription>
                </DialogHeader>
               
                <div className="min-h-0 -mr-2 overflow-y-auto px-2 [scrollbar-color:var(--border)_transparent] [scrollbar-width:thin]">
                    {children({ close: () => setOpen(false), setBusy })}
                </div>                
            </DialogContent>
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
