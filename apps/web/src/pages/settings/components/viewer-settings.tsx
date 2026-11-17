import { Radio } from '@base-ui/react/radio'
import { cn } from 'cn'

import {
    buttonVariants,
    RadioGroup,
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
    Switch,
    useSettings,
} from '@components'
import { MOUSE_PROFILE_IDS, MOUSE_PROFILES } from '@pages/machines/models/mouse-profile-model'

import type { NavigationSpeed } from '../models/settings-model'
import { MouseDiagram } from './mouse-diagram'
import { SettingsRow, SettingsSection } from './settings-layout'

const profileItems = MOUSE_PROFILE_IDS.map((id) => ({ value: id, label: MOUSE_PROFILES[id].label }))

const speedOptions: readonly { value: NavigationSpeed; label: string }[] = [
    { value: 'slow', label: 'Slow' },
    { value: 'normal', label: 'Normal' },
    { value: 'fast', label: 'Fast' },
]

type ToggleKey = 'invertZoom' | 'zoomToCursor' | 'showViewCube'

const toggles: readonly { key: ToggleKey; title: string; description: string }[] = [
    {
        key: 'invertZoom',
        title: 'Invert zoom direction',
        description: 'Reverse the zoom direction of the wheel and zoom drags.',
    },
    {
        key: 'zoomToCursor',
        title: 'Zoom to cursor',
        description: 'Zoom towards the cursor instead of the center of the view.',
    },
    {
        key: 'showViewCube',
        title: 'Show view cube',
        description: 'Cube in the corner of the view to look from a side.',
    },
]

export function ViewerSettings() {
    const { settings, update } = useSettings()
    const profile = MOUSE_PROFILES[settings.mouseProfile]

    return (
        <div className="space-y-10">
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
                            <SelectTrigger
                                className="w-36 shrink-0"
                                aria-label="Navigation profile"
                            >
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
                    <MouseDiagram profile={profile} />
                    {profile.requiresMiddleButton ? (
                        <p className="text-muted-foreground text-xs">Requires a 3-button mouse.</p>
                    ) : null}
                </div>
            </SettingsSection>
            <SettingsSection title="Navigation">
                <SettingsRow title="Speed" description="Speed of rotation, pan and zoom.">
                    <RadioGroup
                        aria-label="Speed"
                        value={settings.navigationSpeed}
                        onValueChange={(value) =>
                            update({ navigationSpeed: value as NavigationSpeed })
                        }
                        className="flex w-auto gap-1"
                    >
                        {speedOptions.map((option) => (
                            <Radio.Root
                                key={option.value}
                                value={option.value}
                                className={cn(
                                    buttonVariants({ variant: 'ghost' }),
                                    'text-muted-foreground data-checked:bg-secondary data-checked:text-secondary-foreground',
                                )}
                            >
                                {option.label}
                            </Radio.Root>
                        ))}
                    </RadioGroup>
                </SettingsRow>
                {toggles.map((toggle) => (
                    <SettingsRow
                        key={toggle.key}
                        title={toggle.title}
                        description={toggle.description}
                    >
                        <Switch
                            aria-label={toggle.title}
                            checked={settings[toggle.key]}
                            onCheckedChange={(checked) => update({ [toggle.key]: checked })}
                        />
                    </SettingsRow>
                ))}
            </SettingsSection>
        </div>
    )
}
