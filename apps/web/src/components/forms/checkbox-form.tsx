import * as React from 'react'
import { getVisibleFieldErrors } from '@utils/field-errors'
import { Checkbox } from '../atomic/atoms'
import { Field, FieldContent, FieldDescription, FieldError } from '../atomic/molecules'
import { FormLabel } from './form-label'
import { useFieldContext } from './form-context'

export type CheckboxFormProps = Omit<
    React.ComponentProps<typeof Checkbox>,
    'checked' | 'defaultChecked' | 'name' | 'onBlur' | 'onCheckedChange' | 'aria-invalid'
> & {
    label: string
    description?: string
    optional?: boolean
    info?: string
}

export function CheckboxForm({
    id,
    label,
    description,
    optional,
    info,
    'aria-describedby': ariaDescribedBy,
    ...props
}: CheckboxFormProps) {
    const field = useFieldContext<boolean>()

    const generatedId = React.useId()
    const checkboxId = id ?? `${generatedId}-checkbox`
    const descriptionId = description ? `${checkboxId}-description` : undefined
    const infoId = info ? `${checkboxId}-info` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${checkboxId}-error` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, infoId, errorId].filter(Boolean).join(' ') || undefined

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
                <FormLabel
                    htmlFor={checkboxId}
                    label={label}
                    optional={optional}
                    info={info}
                    infoId={infoId}
                />
                {description ? (
                    <FieldDescription id={descriptionId}>{description}</FieldDescription>
                ) : null}
                <FieldError id={errorId} errors={errors} />
            </FieldContent>
        </Field>
    )
}
