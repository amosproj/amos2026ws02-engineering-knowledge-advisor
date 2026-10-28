import { createFormHook } from '@tanstack/react-form'
import { fieldContext, formContext } from './form-context'
import { CheckboxForm } from './checkbox-form'
import { InputForm } from './input-form'
import { NativeSelectForm } from './native-select-form'
import { PasswordForm } from './password-form'
import { SubscribeForm } from './subscribe-form'
import { SwitchForm } from './switch-form'
import { TextareaForm } from './textarea-form'
import { ToggleForm } from './toggle-form'

export { useFieldContext, useFormContext } from './form-context'
export type { CheckboxFormProps } from './checkbox-form'
export type { InputFormProps } from './input-form'
export type { NativeSelectFormProps } from './native-select-form'
export type { PasswordFormProps } from './password-form'
export type { SubscribeFormProps } from './subscribe-form'
export type { SwitchFormProps } from './switch-form'
export type { TextareaFormProps } from './textarea-form'
export type { ToggleFormProps } from './toggle-form'

export const { useAppForm, withForm, withFieldGroup } = createFormHook({
    fieldComponents: {
        CheckboxForm,
        InputForm,
        NativeSelectForm,
        PasswordForm,
        SwitchForm,
        TextareaForm,
        ToggleForm,
    },
    formComponents: {
        SubscribeForm,
    },
    fieldContext,
    formContext,
})
