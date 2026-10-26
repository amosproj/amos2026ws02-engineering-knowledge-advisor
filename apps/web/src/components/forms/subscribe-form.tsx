import * as React from 'react'
import { Button, Spinner } from '../atomic/atoms'
import { useFormContext } from './form-context'

export type SubscribeFormProps = Omit<React.ComponentProps<typeof Button>, 'type'> & {
    pendingContent?: React.ReactNode
}

export function SubscribeForm({
    children,
    pendingContent,
    disabled,
    ...props
}: SubscribeFormProps) {
    const form = useFormContext()

    return (
        <form.Subscribe selector={(state) => [state.canSubmit, state.isSubmitting] as const}>
            {([canSubmit, isSubmitting]) => (
                <Button
                    {...props}
                    type="submit"
                    disabled={disabled || !canSubmit || isSubmitting}
                    aria-busy={isSubmitting}
                >
                    {isSubmitting ? (
                        <>
                            <Spinner aria-hidden />
                            {pendingContent ?? children}
                        </>
                    ) : (
                        children
                    )}
                </Button>
            )}
        </form.Subscribe>
    )
}
