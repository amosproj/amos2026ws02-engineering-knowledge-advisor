import * as React from 'react'

import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
    AlertDialogTrigger,
} from '../molecules'

export type ConfirmationPopupProps = {
    title: string
    description: string
    /** Element that opens the popup when clicked. */
    children: React.ReactElement
    onConfirm: () => void
    /** Called when the trigger is clicked, before the popup opens. */
    onClick?: () => void
    /** Called whenever the popup closes, whatever the reason. */
    onClose?: () => void
    onCancel?: () => void
    confirmLabel?: string
    cancelLabel?: string
}

export function ConfirmationPopup({
    title,
    description,
    children,
    onConfirm,
    onClick,
    onClose,
    onCancel,
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
}: ConfirmationPopupProps) {
    const [open, setOpen] = React.useState(false)

    const handleOpenChange = (nextOpen: boolean) => {
        setOpen(nextOpen)
        if (!nextOpen) {
            onClose?.()
        }
    }

    return (
        <AlertDialog open={open} onOpenChange={handleOpenChange}>
            <AlertDialogTrigger render={children} onClick={onClick} />
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>{title}</AlertDialogTitle>
                    <AlertDialogDescription>{description}</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel onClick={onCancel}>{cancelLabel}</AlertDialogCancel>
                    <AlertDialogAction
                        onClick={() => {
                            onConfirm()
                            handleOpenChange(false)
                        }}
                    >
                        {confirmLabel}
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    )
}
