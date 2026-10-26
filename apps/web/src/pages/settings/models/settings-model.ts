import { formOptions } from '@tanstack/react-form'

export type Theme = 'system' | 'light' | 'dark'

/** Values of every settings section; add a field here and in `DEFAULT_SETTINGS`. */
export type SettingsValues = {
    theme: Theme
}

/** Single source of truth for "Restore defaults". */
export const DEFAULT_SETTINGS: SettingsValues = {
    theme: 'system',
}

export const settingsFormOptions = formOptions({
    defaultValues: DEFAULT_SETTINGS,
})
