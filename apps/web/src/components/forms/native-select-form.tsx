import * as React from 'react'
import { getVisibleFieldErrors } from '@utils/field-errors'
import { NativeSelect } from '../atomic/atoms'
import { Field, FieldDescription, FieldError } from '../atomic/molecules'
import { FormLabel } from './form-label'
import { useFieldContext } from './form-context'

export type NativeSelectFormProps = Omit<
    React.ComponentProps<typeof NativeSelect>,
    'value' | 'defaultValue' | 'name' | 'onBlur' | 'onChange' | 'aria-invalid' | 'multiple'
> & {
    label: string
    description?: string
    optional?: boolean
    info?: string
    /** Rendered next to the label, e.g. a "Required" badge. */
    labelAction?: React.ReactNode
}

export function NativeSelectForm({
    id,
    label,
    description,
    optional,
    info,
    labelAction,
    'aria-describedby': ariaDescribedBy,
    ...props
}: NativeSelectFormProps) {
    const field = useFieldContext<string>()

    const generatedId = React.useId()
    const selectId = id ?? `${generatedId}-select`
    const descriptionId = description ? `${selectId}-description` : undefined
    const infoId = info ? `${selectId}-info` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${selectId}-error` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, infoId, errorId].filter(Boolean).join(' ') || undefined

    return (
        <Field data-invalid={errors.length > 0}>
            <FormLabel
                htmlFor={selectId}
                label={label}
                optional={optional}
                info={info}
                infoId={infoId}
                action={labelAction}
            />
            <NativeSelect
                {...props}
                id={selectId}
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
