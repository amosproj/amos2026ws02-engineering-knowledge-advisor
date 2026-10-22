import * as React from 'react'
import { getVisibleFieldErrors } from '@utils/field-errors'
import { Textarea } from '../atomic/atoms'
import { Field, FieldDescription, FieldError, FieldLabel } from '../atomic/molecules'
import { useFieldContext } from './form-context'

export type TextareaFormProps = Omit<
    React.ComponentProps<typeof Textarea>,
    'value' | 'defaultValue' | 'name' | 'onBlur' | 'onChange' | 'aria-invalid'
> & {
    label: string
    description?: string
}

export function TextareaForm({
    id,
    label,
    description,
    'aria-describedby': ariaDescribedBy,
    ...props
}: TextareaFormProps) {
    const field = useFieldContext<string>()

    const generatedId = React.useId()
    const textareaId = id ?? `${generatedId}-textarea`
    const descriptionId = description ? `${textareaId}-description` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${textareaId}-error` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, errorId].filter(Boolean).join(' ') || undefined

    return (
        <Field data-invalid={errors.length > 0}>
            <FieldLabel htmlFor={textareaId}>{label}</FieldLabel>
            <Textarea
                {...props}
                id={textareaId}
                name={field.name}
                value={field.state.value}
                onBlur={field.handleBlur}
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
