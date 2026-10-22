import * as React from 'react'
import { getVisibleFieldErrors } from '@utils'
import { Toggle } from '../atomic/atoms'
import { Field, FieldDescription, FieldError } from '../atomic/molecules'
import { useFieldContext } from './form-context'

export type ToggleFormProps = Omit<
    React.ComponentProps<typeof Toggle>,
    | 'pressed'
    | 'defaultPressed'
    | 'onBlur'
    | 'onPressedChange'
    | 'aria-invalid'
    | 'children'
    | 'type'
    | 'value'
> & {
    label: string
    description?: string
    children?: React.ReactNode
}

export function ToggleForm({
    id,
    label,
    description,
    children,
    'aria-describedby': ariaDescribedBy,
    ...props
}: ToggleFormProps) {
    const field = useFieldContext<boolean>()

    const generatedId = React.useId()
    const toggleId = id ?? `${generatedId}-toggle`
    const descriptionId = description ? `${toggleId}-description` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${toggleId}-error` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, errorId].filter(Boolean).join(' ') || undefined

    return (
        <Field data-invalid={errors.length > 0}>
            <Toggle
                {...props}
                id={toggleId}
                type="button"
                pressed={field.state.value}
                onBlur={field.handleBlur}
                onPressedChange={field.handleChange}
                aria-label={label}
                aria-invalid={errors.length > 0}
                aria-describedby={describedBy}
            >
                {children ?? label}
            </Toggle>
            {description ? (
                <FieldDescription id={descriptionId}>{description}</FieldDescription>
            ) : null}
            <FieldError id={errorId} errors={errors} />
        </Field>
    )
}
