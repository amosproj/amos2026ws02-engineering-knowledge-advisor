import { Button, withForm } from '@components'
import { useTheme } from '@components/providers'

import { settingsFormOptions, type Theme } from '../models/settings-model'
import { SettingsRow, SettingsSection } from './settings-layout'

const themeOptions: readonly { value: Theme; label: string }[] = [
    { value: 'system', label: 'System' },
    { value: 'light', label: 'Light' },
    { value: 'dark', label: 'Dark' },
]

export const GeneralSettings = withForm({
    ...settingsFormOptions,
    render: function Render({ form }) {
        const { setTheme } = useTheme()

        return (
            <div className="space-y-10">
                <h1 className="text-2xl font-semibold tracking-tight">General</h1>

                <SettingsSection title="Appearance">
                    <form.AppField
                        name="theme"
                        listeners={{ onChange: ({ value }) => setTheme(value) }}
                    >
                        {(field) => (
                            <SettingsRow
                                title="Theme"
                                description="System follows the operating system light or dark appearance."
                            >
                                <div
                                    role="radiogroup"
                                    aria-label="Theme"
                                    className="flex items-center gap-1"
                                >
                                    {themeOptions.map((option) => {
                                        const selected = field.state.value === option.value

                                        return (
                                            <Button
                                                key={option.value}
                                                type="button"
                                                role="radio"
                                                aria-checked={selected}
                                                variant={selected ? 'secondary' : 'ghost'}
                                                className={selected ? '' : 'text-muted-foreground'}
                                                onBlur={field.handleBlur}
                                                onClick={() => field.handleChange(option.value)}
                                            >
                                                {option.label}
                                            </Button>
                                        )
                                    })}
                                </div>
                            </SettingsRow>
                        )}
                    </form.AppField>
                </SettingsSection>
            </div>
        )
    },
})
