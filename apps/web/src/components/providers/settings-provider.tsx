import * as React from 'react'

import {
    DEFAULT_SETTINGS,
    parseStoredSettings,
    type Settings,
} from '@pages/settings/models/settings-model'

const STORAGE_KEY = 'settings'

type SettingsContextValue = {
    settings: Settings
    update: (partial: Partial<Settings>) => void
    reset: () => void
}

const SettingsContext = React.createContext<SettingsContextValue | undefined>(undefined)

function readStoredSettings() {
    try {
        return parseStoredSettings(localStorage.getItem(STORAGE_KEY))
    } catch {
        return DEFAULT_SETTINGS
    }
}

export function SettingsProvider({ children }: { children: React.ReactNode }) {
    const [settings, setSettings] = React.useState(readStoredSettings)

    React.useEffect(() => {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
        } catch {
            // Storage unavailable: settings stay in memory for this session
        }
    }, [settings])

    React.useEffect(() => {
        const handleStorage = (event: StorageEvent) => {
            if (event.storageArea !== localStorage) return
            if (event.key !== STORAGE_KEY && event.key !== null) return
            setSettings(parseStoredSettings(event.newValue))
        }
        window.addEventListener('storage', handleStorage)
        return () => window.removeEventListener('storage', handleStorage)
    }, [])

    const update = React.useCallback((partial: Partial<Settings>) => {
        setSettings((current) => ({ ...current, ...partial }))
    }, [])

    const reset = React.useCallback(() => setSettings(DEFAULT_SETTINGS), [])

    const value = React.useMemo(() => ({ settings, update, reset }), [settings, update, reset])

    return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
}

export function useSettings() {
    const context = React.useContext(SettingsContext)
    if (!context) throw new Error('useSettings must be used within a SettingsProvider')
    return context
}
