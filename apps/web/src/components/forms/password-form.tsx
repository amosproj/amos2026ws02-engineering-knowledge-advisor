import * as React from 'react'
import { ViewIcon, ViewOffIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import { getVisibleFieldErrors } from '@utils'
import {
    Field,
    FieldDescription,
    FieldError,
    FieldLabel,
    InputGroup,
    InputGroupAddon,
    InputGroupButton,
    InputGroupInput,
} from '../atomic/molecules'
import { useFieldContext } from './form-context'

export type PasswordFormProps = Omit<
    React.ComponentProps<typeof InputGroupInput>,
    'type' | 'value' | 'defaultValue' | 'name' | 'onBlur' | 'onChange' | 'aria-invalid'
> & {
    label: string
    description?: React.ReactNode
    /** Rendered next to the label, e.g. a "Forgot password?" link. */
    labelAction?: React.ReactNode
    groupClassName?: string
}

export function PasswordForm({
    id,
    label,
    description,
    labelAction,
    groupClassName,
    'aria-describedby': ariaDescribedBy,
    ...props
}: PasswordFormProps) {
    const field = useFieldContext<string>()
    const [visible, setVisible] = React.useState(false)

    const generatedId = React.useId()
    const inputId = id ?? `${generatedId}-input`
    const errors = getVisibleFieldErrors(field.state.meta.errors, field.state.meta.isTouched)
    const errorId = errors.length > 0 ? `${inputId}-error` : undefined
    // Password hints usually restate the rule that failed, so the error replaces them.
    const showDescription = Boolean(description) && errors.length === 0
    const descriptionId = showDescription ? `${inputId}-description` : undefined

    const describedBy =
        [ariaDescribedBy, descriptionId, errorId].filter(Boolean).join(' ') || undefined

    return (
        <Field data-invalid={errors.length > 0}>
            <div className="flex items-center justify-between gap-3">
                <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
                {labelAction}
            </div>
            <InputGroup className={groupClassName}>
                <InputGroupInput
                    {...props}
                    id={inputId}
                    name={field.name}
                    type={visible ? 'text' : 'password'}
                    value={field.state.value}
                    onBlur={field.handleBlur}
                    onChange={(event) => field.handleChange(event.target.value)}
                    aria-invalid={errors.length > 0}
                    aria-describedby={describedBy}
                />
                <InputGroupAddon align="inline-end">
                    <InputGroupButton
                        size="icon-sm"
                        className="text-muted-foreground hover:text-foreground"
                        aria-label={visible ? 'Hide password' : 'Show password'}
                        aria-pressed={visible}
                        aria-controls={inputId}
                        onClick={() => setVisible((current) => !current)}
                    >
                        <HugeiconsIcon
                            icon={visible ? ViewOffIcon : ViewIcon}
                            aria-hidden
                            data-slot="icon"
                        />
                    </InputGroupButton>
                </InputGroupAddon>
            </InputGroup>
            {showDescription ? (
                <FieldDescription id={descriptionId}>{description}</FieldDescription>
            ) : null}
            <FieldError id={errorId} errors={errors} />
        </Field>
    )
}
