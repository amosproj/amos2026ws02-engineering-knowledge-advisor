import { useState } from 'react'
import { cn } from 'cn'

import { useAppForm } from '@components'
import { useTheme } from '@components/providers'

import { GeneralSettings } from './components/general-settings'
import { ResetSettings } from './components/reset-settings'
import { DEFAULT_SETTINGS, type SettingsValues } from './models/settings-model'

const sections = [{ id: 'general', label: 'General' }] as const

export const SettingsPage = () => {
    const active = sections[0]
    const { theme, setTheme } = useTheme()

    const [initialValues] = useState<SettingsValues>(() => ({ ...DEFAULT_SETTINGS, theme }))

    const form = useAppForm({
        defaultValues: initialValues,
        onSubmit: () => {},
    })

    const restoreDefaults = () => {
        form.reset(DEFAULT_SETTINGS)
        setTheme(DEFAULT_SETTINGS.theme)
    }

    return (
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-2 py-6 md:flex-row md:gap-16 md:py-10">
            <nav aria-label="Settings" className="flex flex-col gap-1 md:w-44 md:shrink-0">
                {sections.map((section) => (
                    <button
                        key={section.id}
                        type="button"
                        aria-current={section.id === active.id ? 'page' : undefined}
                        className={cn(
                            'rounded-lg px-3 py-1.5 text-left text-sm font-medium transition-colors',
                            section.id === active.id
                                ? 'bg-muted text-foreground'
                                : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
                        )}
                    >
                        {section.label}
                    </button>
                ))}
            </nav>
            <form
                className="min-w-0 flex-1 space-y-10"
                onSubmit={(event) => {
                    event.preventDefault()
                    void form.handleSubmit()
                }}
            >
                <GeneralSettings form={form} />
                <ResetSettings onConfirm={restoreDefaults} />
            </form>
        </div>
    )
}
