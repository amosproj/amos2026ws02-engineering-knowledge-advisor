import * as React from 'react'
import { getVisibleFieldErrors } from '@utils'
import { Input } from '../atomic/atoms'
import { Field, FieldDescription, FieldError, FieldLabel } from '../atomic/molecules'
import { useFieldContext } from './form-context'

export type InputFormProps = Omit<
    React.ComponentProps<typeof Input>,
    'value' | 'defaultValue' | 'name' | 'onBlur' | 'onChange' | 'aria-invalid'
> & {
    label: string
    description?: string
    /** Rendered next to the label, e.g. a "Last used" badge. */
    labelAction?: React.ReactNode
    onValueBlur?: (value: string) => void
}

export function InputForm({
    id,
    label,
    description,
    labelAction,
    onValueBlur,
    'aria-describedby': ariaDescribedBy,
    ...props
}: InputFormProps) {
    const field = useFieldContext<string>()

    const generatedId = React.useId()
    const inputId = id ?? `${generatedId}-input`
    const descriptionId = description ? `${inputId}-description` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${inputId}-error` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, errorId].filter(Boolean).join(' ') || undefined

    return (
        <Field data-invalid={errors.length > 0}>
            {labelAction ? (
                <div className="flex items-center justify-between gap-3">
                    <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
                    {labelAction}
                </div>
            ) : (
                <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
            )}
            <Input
                {...props}
                id={inputId}
                name={field.name}
                value={field.state.value}
                onBlur={() => {
                    field.handleBlur()
                    onValueBlur?.(field.state.value)
                }}
                onChange={(event) => field.handleChange(event.target.value)}
                aria-invalid={errors.length > 0}
                aria-describedby={describedBy}
            />
            {description ? (
                <FieldDescription id={descriptionId}>{description}</FieldDescription>
            ) : null}
            <FieldError id={errorId} errors={errors} />
        </Field>
    )
}
