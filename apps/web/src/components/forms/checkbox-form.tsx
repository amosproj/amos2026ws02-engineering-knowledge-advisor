import * as React from 'react'
import { getVisibleFieldErrors } from '@utils/field-errors'
import { Checkbox } from '../atomic/atoms'
import { Field, FieldContent, FieldDescription, FieldError, FieldLabel } from '../atomic/molecules'
import { useFieldContext } from './form-context'

export type CheckboxFormProps = Omit<
    React.ComponentProps<typeof Checkbox>,
    'checked' | 'defaultChecked' | 'name' | 'onBlur' | 'onCheckedChange' | 'aria-invalid'
> & {
    label: string
    description?: string
}

export function CheckboxForm({
    id,
    label,
    description,
    'aria-describedby': ariaDescribedBy,
    ...props
}: CheckboxFormProps) {
    const field = useFieldContext<boolean>()

    const generatedId = React.useId()
    const checkboxId = id ?? `${generatedId}-checkbox`
    const descriptionId = description ? `${checkboxId}-description` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${checkboxId}-error` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, errorId].filter(Boolean).join(' ') || undefined

    return (
        <Field orientation="horizontal" data-invalid={errors.length > 0}>
            <Checkbox
                {...props}
                id={checkboxId}
                name={field.name}
                checked={field.state.value}
                onBlur={field.handleBlur}
                onCheckedChange={field.handleChange}
                aria-invalid={errors.length > 0}
                aria-describedby={describedBy}
            />
            <FieldContent>
                <FieldLabel htmlFor={checkboxId}>{label}</FieldLabel>
                {description ? (
                    <FieldDescription id={descriptionId}>{description}</FieldDescription>
                ) : null}
                <FieldError id={errorId} errors={errors} />
            </FieldContent>
        </Field>
    )
}
