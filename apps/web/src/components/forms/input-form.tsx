import * as React from 'react'
import { getVisibleFieldErrors } from '@utils/field-errors'
import { Input } from '../atomic/atoms'
import { Field, FieldDescription, FieldError } from '../atomic/molecules'
import { FormLabel } from './form-label'
import { useFieldContext } from './form-context'

export type InputFormProps = Omit<
    React.ComponentProps<typeof Input>,
    'value' | 'defaultValue' | 'name' | 'onBlur' | 'onChange' | 'aria-invalid'
> & {
    label: string
    description?: string
    optional?: boolean
    info?: string
    /** Rendered next to the label, e.g. a "Last used" badge. */
    labelAction?: React.ReactNode
    onValueBlur?: (value: string) => void
}

export function InputForm({
    id,
    label,
    description,
    optional,
    info,
    labelAction,
    onValueBlur,
    'aria-describedby': ariaDescribedBy,
    ...props
}: InputFormProps) {
    const field = useFieldContext<string>()

    const generatedId = React.useId()
    const inputId = id ?? `${generatedId}-input`
    const descriptionId = description ? `${inputId}-description` : undefined
    const infoId = info ? `${inputId}-info` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${inputId}-error` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, infoId, errorId].filter(Boolean).join(' ') || undefined

    return (
        <Field data-invalid={errors.length > 0}>
            <FormLabel
                htmlFor={inputId}
                label={label}
                optional={optional}
                info={info}
                infoId={infoId}
                action={labelAction}
            />
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
