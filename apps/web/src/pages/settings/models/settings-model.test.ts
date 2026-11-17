import { describe, expect, it } from 'vitest'

import { DEFAULT_SETTINGS, parseStoredSettings, settingsSearchSchema } from './settings-model'

describe('parseStoredSettings', () => {
    it('falls back to the defaults when nothing usable is stored', () => {
        for (const raw of [null, '{not json', 'null', '[]', '42', '"dark"']) {
            expect(parseStoredSettings(raw)).toEqual(DEFAULT_SETTINGS)
        }
    })

    it('replaces only the invalid fields with their default', () => {
        const raw = JSON.stringify({
            theme: 'dark',
            sidebarOpen: 'yes',
            mouseProfile: 'maya',
            navigationSpeed: 'fast',
            invertZoom: 1,
            zoomToCursor: false,
        })

        expect(parseStoredSettings(raw)).toEqual({
            ...DEFAULT_SETTINGS,
            theme: 'dark',
            navigationSpeed: 'fast',
            zoomToCursor: false,
        })
    })
})

describe('settingsSearchSchema', () => {
    it('drops an unknown section so the page opens the general tab', () => {
        expect(settingsSearchSchema.parse({ section: 'unknown' })).toEqual({ section: undefined })
    })
})
