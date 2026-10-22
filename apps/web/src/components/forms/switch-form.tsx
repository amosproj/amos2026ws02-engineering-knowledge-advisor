import * as React from 'react'
import { getVisibleFieldErrors } from '@utils/field-errors'
import { Switch } from '../atomic/atoms'
import { Field, FieldContent, FieldDescription, FieldError, FieldLabel } from '../atomic/molecules'
import { useFieldContext } from './form-context'

export type SwitchFormProps = Omit<
    React.ComponentProps<typeof Switch>,
    'checked' | 'defaultChecked' | 'name' | 'onBlur' | 'onCheckedChange' | 'aria-invalid'
> & {
    label: string
    description?: string
}

export function SwitchForm({
    id,
    label,
    description,
    'aria-describedby': ariaDescribedBy,
    ...props
}: SwitchFormProps) {
    const field = useFieldContext<boolean>()

    const generatedId = React.useId()
    const switchId = id ?? `${generatedId}-switch`
    const descriptionId = description ? `${switchId}-description` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${switchId}-error` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, errorId].filter(Boolean).join(' ') || undefined

    return (
        <Field orientation="horizontal" data-invalid={errors.length > 0}>
            <FieldContent>
                <FieldLabel htmlFor={switchId}>{label}</FieldLabel>
                {description ? (
                    <FieldDescription id={descriptionId}>{description}</FieldDescription>
                ) : null}
                <FieldError id={errorId} errors={errors} />
            </FieldContent>
            <Switch
                {...props}
                id={switchId}
                name={field.name}
                checked={field.state.value}
                onBlur={field.handleBlur}
                onCheckedChange={field.handleChange}
                aria-invalid={errors.length > 0}
                aria-describedby={describedBy}
            />
        </Field>
    )
}
