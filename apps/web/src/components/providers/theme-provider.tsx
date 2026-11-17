import * as React from 'react'

import type { Theme } from '@pages/settings/models/settings-model'

import { useSettings } from './settings-provider'

type ResolvedTheme = 'dark' | 'light'

const COLOR_SCHEME_QUERY = '(prefers-color-scheme: dark)'

function getSystemTheme(): ResolvedTheme {
    return window.matchMedia(COLOR_SCHEME_QUERY).matches ? 'dark' : 'light'
}

function disableTransitionsTemporarily() {
    const style = document.createElement('style')
    style.appendChild(
        document.createTextNode(
            '*,*::before,*::after{-webkit-transition:none!important;transition:none!important}',
        ),
    )
    document.head.appendChild(style)

    return () => {
        window.getComputedStyle(document.body)
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                style.remove()
            })
        })
    }
}

function isEditableTarget(target: EventTarget | null) {
    if (!(target instanceof HTMLElement)) return false
    if (target.isContentEditable) return true
    return target.closest("input, textarea, select, [contenteditable='true']") !== null
}

function applyTheme(theme: Theme) {
    const root = document.documentElement
    const restoreTransitions = disableTransitionsTemporarily()
    root.classList.remove('light', 'dark')
    root.classList.add(theme === 'system' ? getSystemTheme() : theme)
    restoreTransitions()
}

/** Applies the theme setting to the document and toggles it with the "d" key. */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
    const { settings, update } = useSettings()
    const theme = settings.theme

    React.useEffect(() => {
        applyTheme(theme)
        if (theme !== 'system') return

        const mediaQuery = window.matchMedia(COLOR_SCHEME_QUERY)
        const handleChange = () => applyTheme('system')
        mediaQuery.addEventListener('change', handleChange)
        return () => mediaQuery.removeEventListener('change', handleChange)
    }, [theme])

    React.useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.repeat || event.metaKey || event.ctrlKey || event.altKey) return
            if (isEditableTarget(event.target)) return
            if (event.key.toLowerCase() !== 'd') return

            const shown = theme === 'system' ? getSystemTheme() : theme
            update({ theme: shown === 'dark' ? 'light' : 'dark' })
        }

        window.addEventListener('keydown', handleKeyDown)
        return () => window.removeEventListener('keydown', handleKeyDown)
    }, [theme, update])

    return children
}
