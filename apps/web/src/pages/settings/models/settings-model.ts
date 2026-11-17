import { z } from 'zod'

import { MOUSE_PROFILE_IDS } from '@pages/machines/models/mouse-profile-model'

export const THEMES = ['system', 'light', 'dark'] as const
export type Theme = (typeof THEMES)[number]

const settingsSchema = z.object({
    theme: z.enum(THEMES).catch('system'),
    sidebarOpen: z.boolean().catch(true),
    mouseProfile: z.enum(MOUSE_PROFILE_IDS).catch('default'),
})

export type Settings = z.output<typeof settingsSchema>

export const DEFAULT_SETTINGS: Settings = settingsSchema.parse({})

/** Invalid fields fall back to their default, the valid ones are kept. */
export function parseStoredSettings(raw: string | null): Settings {
    if (raw === null) return DEFAULT_SETTINGS
    try {
        const result = settingsSchema.safeParse(JSON.parse(raw))
        return result.success ? result.data : DEFAULT_SETTINGS
    } catch {
        return DEFAULT_SETTINGS
    }
}

export const SETTINGS_SECTIONS = [
    { id: 'general', label: 'General' },
    { id: 'viewer', label: '3D Viewer' },
] as const

export const settingsSearchSchema = z.object({
    section: z.enum(['general', 'viewer']).optional().catch(undefined),
})
