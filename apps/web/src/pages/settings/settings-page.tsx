import { Link, useSearch } from '@tanstack/react-router'
import { cn } from 'cn'

import { useSettings } from '@components'

import { GeneralSettings } from './components/general-settings'
import { ResetSettings } from './components/reset-settings'
import { ViewerSettings } from './components/viewer-settings'
import { SETTINGS_SECTIONS } from './models/settings-model'

export const SettingsPage = () => {
    const { section = 'general' } = useSearch({ from: '/settings' })
    const { reset } = useSettings()
    const active = SETTINGS_SECTIONS.find((item) => item.id === section) ?? SETTINGS_SECTIONS[0]

    return (
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-6 md:flex-row md:gap-16 md:px-6 md:py-10">
            <nav aria-label="Settings" className="flex flex-col gap-1 md:w-44 md:shrink-0">
                {SETTINGS_SECTIONS.map((item) => (
                    <Link
                        key={item.id}
                        to="/settings"
                        search={{ section: item.id }}
                        aria-current={item.id === active.id ? 'page' : undefined}
                        className={cn(
                            'rounded-lg px-3 py-1.5 text-left text-sm font-medium transition-colors',
                            item.id === active.id
                                ? 'bg-muted text-foreground'
                                : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
                        )}
                    >
                        {item.label}
                    </Link>
                ))}
            </nav>
            <div className="min-w-0 flex-1 space-y-10">
                <h1 className="text-2xl font-semibold tracking-tight">{active.label}</h1>
                {active.id === 'general' ? <GeneralSettings /> : <ViewerSettings />}
                <ResetSettings onConfirm={reset} />
            </div>
        </div>
    )
}
