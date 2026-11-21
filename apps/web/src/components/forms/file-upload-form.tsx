import * as React from 'react'
import { getVisibleFieldErrors } from '@utils/field-errors'
import { Field, FieldDescription, FieldError } from '../atomic/molecules'
import { FileUpload, type FileUploadProps } from '../atomic/organisms/file-upload'
import { FormLabel } from './form-label'
import { useFieldContext } from './form-context'

type FileUploadFieldProps = Pick<
    FileUploadProps,
    'id' | 'accept' | 'maxSize' | 'disabled' | 'aria-describedby'
> & {
    label: string
    description?: string
    optional?: boolean
    info?: string
}

export type FileUploadFormProps = FileUploadFieldProps &
    ({ mode: 'single'; maxFiles?: never } | { mode: 'multiple'; maxFiles?: number })

export function FileUploadForm({
    id,
    label,
    description,
    optional,
    info,
    mode,
    maxFiles,
    'aria-describedby': ariaDescribedBy,
    ...props
}: FileUploadFormProps) {
    const field = useFieldContext<File | File[] | null>()
    const { value } = field.state

    const generatedId = React.useId()
    const zoneId = id ?? `${generatedId}-zone`
    const descriptionId = description ? `${zoneId}-description` : undefined
    const infoId = info ? `${zoneId}-info` : undefined

    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const fieldErrorId = errors.length > 0 ? `${zoneId}-field-error` : undefined

    const uploadProps = {
        ...props,
        id: zoneId,
        invalid: errors.length > 0,
        onBlur: field.handleBlur,
        'aria-describedby':
            [ariaDescribedBy, descriptionId, infoId, fieldErrorId].filter(Boolean).join(' ') ||
            undefined,
    }

    return (
        <Field data-invalid={errors.length > 0}>
            <FormLabel
                htmlFor={zoneId}
                label={label}
                optional={optional}
                info={info}
                infoId={infoId}
            />
            {mode === 'multiple' ? (
                <FileUpload
                    {...uploadProps}
                    mode="multiple"
                    maxFiles={maxFiles}
                    value={Array.isArray(value) ? value : value ? [value] : []}
                    onChange={(files) => field.handleChange(files)}
                />
            ) : (
                <FileUpload
                    {...uploadProps}
                    mode="single"
                    value={Array.isArray(value) ? (value[0] ?? null) : value}
                    onChange={(file) => field.handleChange(file)}
                />
            )}
            {description ? (
                <FieldDescription id={descriptionId}>{description}</FieldDescription>
            ) : null}
            <FieldError id={fieldErrorId} errors={errors} />
        </Field>
    )
}
