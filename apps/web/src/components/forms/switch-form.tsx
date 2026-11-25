import * as React from 'react'
import { getVisibleFieldErrors } from '@utils/field-errors'
import { Switch } from '../atomic/atoms'
import { Field, FieldContent, FieldDescription, FieldError } from '../atomic/molecules'
import { FormLabel } from './form-label'
import { useFieldContext } from './form-context'

export type SwitchFormProps = Omit<
    React.ComponentProps<typeof Switch>,
    'checked' | 'defaultChecked' | 'name' | 'onBlur' | 'onCheckedChange' | 'aria-invalid'
> & {
    label: string
    description?: string
    optional?: boolean
    info?: string
}

export function SwitchForm({
    id,
    label,
    description,
    optional,
    info,
    'aria-describedby': ariaDescribedBy,
    ...props
}: SwitchFormProps) {
    const field = useFieldContext<boolean>()

    const generatedId = React.useId()
    const switchId = id ?? `${generatedId}-switch`
    const descriptionId = description ? `${switchId}-description` : undefined
    const infoId = info ? `${switchId}-info` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${switchId}-error` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, infoId, errorId].filter(Boolean).join(' ') || undefined

    return (
        <Field orientation="horizontal" data-invalid={errors.length > 0}>
            <FieldContent>
                <FormLabel
                    htmlFor={switchId}
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
