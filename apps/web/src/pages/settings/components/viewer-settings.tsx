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

import type { NavigationSpeed, SelectionStyle } from '../models/settings-model'
import { MouseDiagram } from './mouse-diagram'
import { SettingsRow, SettingsSection } from './settings-layout'

const profileItems = MOUSE_PROFILE_IDS.map((id) => ({ value: id, label: MOUSE_PROFILES[id].label }))

const speedOptions: readonly { value: NavigationSpeed; label: string }[] = [
    { value: 'slow', label: 'Slow' },
    { value: 'normal', label: 'Normal' },
    { value: 'fast', label: 'Fast' },
]

const selectionStyleOptions: readonly { value: SelectionStyle; label: string }[] = [
    { value: 'opaque', label: 'Opaque' },
    { value: 'sketch', label: 'Sketch' },
]

type Toggle = {
    key: 'invertZoom' | 'zoomToCursor' | 'showViewCube' | 'focusOnSelect'
    title: string
    description: string
}

const navigationToggles: readonly Toggle[] = [
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

const selectionToggles: readonly Toggle[] = [
    {
        key: 'focusOnSelect',
        title: 'Frame the selected part',
        description: 'Move the view to the part selected in the assembly tree.',
    },
]

type ViewerSettingsProps = {
    columns?: boolean
}

export function ViewerSettings({ columns = false }: ViewerSettingsProps) {
    const { settings, update } = useSettings()
    const profile = MOUSE_PROFILES[settings.mouseProfile]

    const mouse = (
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
                <MouseDiagram profile={profile} />
                {profile.requiresMiddleButton ? (
                    <p className="text-muted-foreground text-xs">Requires a 3-button mouse.</p>
                ) : null}
            </div>
        </SettingsSection>
    )
    const navigation = (
        <SettingsSection title="Navigation">
            <SettingsRow title="Speed" description="Speed of rotation, pan and zoom.">
                <Choices
                    label="Speed"
                    options={speedOptions}
                    value={settings.navigationSpeed}
                    onChange={(navigationSpeed) => update({ navigationSpeed })}
                />
            </SettingsRow>
            <ToggleRows toggles={navigationToggles} />
        </SettingsSection>
    )
    const selection = (
        <SettingsSection title="Selection">
            <SettingsRow
                title="Other parts"
                description="How the parts around the selected one are drawn."
            >
                <Choices
                    label="Other parts"
                    options={selectionStyleOptions}
                    value={settings.selectionStyle}
                    onChange={(selectionStyle) => update({ selectionStyle })}
                />
            </SettingsRow>
            <ToggleRows toggles={selectionToggles} />
        </SettingsSection>
    )

    return columns ? (
        <div className="grid gap-10 md:grid-cols-2">
            <div className="space-y-10">
                {mouse}
                {selection}
            </div>
            {navigation}
        </div>
    ) : (
        <div className="space-y-10">
            {mouse}
            {navigation}
            {selection}
        </div>
    )
}

type ChoicesProps<T extends string> = {
    label: string
    options: readonly { value: T; label: string }[]
    value: T
    onChange: (value: T) => void
}

function Choices<T extends string>({ label, options, value, onChange }: ChoicesProps<T>) {
    return (
        <RadioGroup
            aria-label={label}
            value={value}
            onValueChange={(next) => onChange(next as T)}
            className="flex w-auto gap-1"
        >
            {options.map((option) => (
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
    )
}

function ToggleRows({ toggles }: { toggles: readonly Toggle[] }) {
    const { settings, update } = useSettings()

    return toggles.map((toggle) => (
        <SettingsRow key={toggle.key} title={toggle.title} description={toggle.description}>
            <Switch
                aria-label={toggle.title}
                checked={settings[toggle.key]}
                onCheckedChange={(checked) => update({ [toggle.key]: checked })}
            />
        </SettingsRow>
    ))
}
