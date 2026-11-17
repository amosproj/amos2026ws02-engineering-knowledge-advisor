import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
    useSettings,
} from '@components'
import {
    MOUSE_PROFILE_IDS,
    MOUSE_PROFILES,
    type MouseAction,
    type MouseProfile,
} from '@pages/machines/models/mouse-profile-model'

import { SettingsSection } from './settings-layout'

const profileItems = MOUSE_PROFILE_IDS.map((id) => ({ value: id, label: MOUSE_PROFILES[id].label }))

const actionLabels: Record<MouseAction, string> = {
    rotate: 'Rotate',
    pan: 'Pan',
    zoom: 'Zoom',
    none: 'None',
}

const buttonLabels = { left: 'Left drag', middle: 'Middle drag', right: 'Right drag' } as const
const modifierPrefixes = { plain: '', shift: 'Shift + ', ctrl: 'Ctrl + ' } as const

function describeProfile(profile: MouseProfile) {
    const rows: { input: string; action: MouseAction }[] = []
    for (const button of ['left', 'middle', 'right'] as const) {
        for (const modifier of ['plain', 'shift', 'ctrl'] as const) {
            const action = profile.buttons[button][modifier]
            if (!action || action === 'none') continue
            rows.push({ input: modifierPrefixes[modifier] + buttonLabels[button], action })
        }
    }
    rows.push({ input: 'Wheel', action: profile.wheel })
    return rows
}

export function ViewerSettings() {
    const { settings, update } = useSettings()
    const profile = MOUSE_PROFILES[settings.mouseProfile]

    return (
        <SettingsSection title="Mouse">
            <div className="bg-card space-y-4 rounded-xl border px-5 py-4">
                <div className="flex items-center justify-between gap-6">
                    <div className="space-y-1">
                        <p className="text-sm font-medium">Navigation profile</p>
                        <p className="text-muted-foreground text-sm">
                            Mouse buttons used to move the 3D view, like in your CAD software.
                        </p>
                    </div>
                    <Select
                        items={profileItems}
                        value={settings.mouseProfile}
                        onValueChange={(value) => {
                            if (value) update({ mouseProfile: value })
                        }}
                    >
                        <SelectTrigger className="w-36 shrink-0" aria-label="Navigation profile">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {profileItems.map((item) => (
                                <SelectItem key={item.value} value={item.value}>
                                    {item.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <dl className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-1 text-sm">
                    {describeProfile(profile).map((row) => (
                        <div key={row.input} className="contents">
                            <dt className="text-muted-foreground">{row.input}</dt>
                            <dd>{actionLabels[row.action]}</dd>
                        </div>
                    ))}
                </dl>
                {profile.requiresMiddleButton ? (
                    <p className="text-muted-foreground text-xs">Requires a 3-button mouse.</p>
                ) : null}
            </div>
        </SettingsSection>
    )
}
