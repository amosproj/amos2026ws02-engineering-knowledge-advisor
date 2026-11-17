import { Button, useSettings } from '@components'

import type { Theme } from '../models/settings-model'
import { SettingsRow, SettingsSection } from './settings-layout'

const themeOptions: readonly { value: Theme; label: string }[] = [
    { value: 'system', label: 'System' },
    { value: 'light', label: 'Light' },
    { value: 'dark', label: 'Dark' },
]

export function GeneralSettings() {
    const { settings, update } = useSettings()

    return (
        <SettingsSection title="Appearance">
            <SettingsRow
                title="Theme"
                description="System follows the operating system light or dark appearance."
            >
                <div role="radiogroup" aria-label="Theme" className="flex items-center gap-1">
                    {themeOptions.map((option) => {
                        const selected = settings.theme === option.value

                        return (
                            <Button
                                key={option.value}
                                type="button"
                                role="radio"
                                aria-checked={selected}
                                variant={selected ? 'secondary' : 'ghost'}
                                className={selected ? '' : 'text-muted-foreground'}
                                onClick={() => update({ theme: option.value })}
                            >
                                {option.label}
                            </Button>
                        )
                    })}
                </div>
            </SettingsRow>
        </SettingsSection>
    )
}
