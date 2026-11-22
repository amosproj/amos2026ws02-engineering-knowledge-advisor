import { useId, type ReactNode } from 'react'
import { Radio } from '@base-ui/react/radio'
import { cn } from 'cn'

import {
    buttonVariants,
    InfoTip,
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
    info?: string
}

const navigationToggles: readonly Toggle[] = [
    {
        key: 'invertZoom',
        title: 'Invert zoom direction',
    },
    {
        key: 'zoomToCursor',
        title: 'Zoom to cursor',
        info: 'Zoom towards the cursor instead of the center of the view.',
    },
    {
        key: 'showViewCube',
        title: 'Show view cube',
    },
]

const selectionToggles: readonly Toggle[] = [
    {
        key: 'focusOnSelect',
        title: 'Frame the selected part',
        info: 'Move the view to the part selected in the assembly tree.',
    },
]

type ViewerSettingsProps = {
    columns?: boolean
    children?: ReactNode
}

export function ViewerSettings({ columns = false, children }: ViewerSettingsProps) {
    const { settings, update } = useSettings()
    const profile = MOUSE_PROFILES[settings.mouseProfile]
    const profileDescriptionId = useId()
    const unselectedDescriptionId = useId()

    const mouse = (
        <SettingsSection title="Mouse">
            <SettingsRow
                title="Navigation profile"
                info={
                    <InfoTip label="About navigation profile" descriptionId={profileDescriptionId}>
                        Mouse buttons used to move the 3D view, like in your CAD software.
                    </InfoTip>
                }
            >
                <Select
                    items={profileItems}
                    value={settings.mouseProfile}
                    onValueChange={(value) => {
                        if (value) update({ mouseProfile: value })
                    }}
                >
                    <SelectTrigger
                        className="w-36"
                        aria-label="Navigation profile"
                        aria-describedby={profileDescriptionId}
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
            </SettingsRow>
            <div className="space-y-4 px-5 py-4">
                <MouseDiagram profile={profile} />
                {profile.requiresMiddleButton ? (
                    <p className="text-muted-foreground text-xs">Requires a 3-button mouse.</p>
                ) : null}
            </div>
        </SettingsSection>
    )
    const navigation = (
        <SettingsSection title="Navigation">
            <SettingsRow title="Speed">
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
                title="Unselected parts"
                info={
                    <InfoTip label="About unselected parts" descriptionId={unselectedDescriptionId}>
                        How the other parts are drawn when a part is selected. Sketch draws only
                        their edges so the selection stands out.
                    </InfoTip>
                }
            >
                <Choices
                    label="Unselected parts"
                    describedBy={unselectedDescriptionId}
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
            <div className="space-y-10">
                {navigation}
                {children}
            </div>
        </div>
    ) : (
        <div className="space-y-10">
            {mouse}
            {navigation}
            {selection}
            {children}
        </div>
    )
}

type ChoicesProps<T extends string> = {
    label: string
    options: readonly { value: T; label: string }[]
    value: T
    onChange: (value: T) => void
    describedBy?: string
}

function Choices<T extends string>({
    label,
    options,
    value,
    onChange,
    describedBy,
}: ChoicesProps<T>) {
    return (
        <RadioGroup
            aria-label={label}
            aria-describedby={describedBy}
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
    return toggles.map((toggle) => <ToggleRow key={toggle.key} toggle={toggle} />)
}

function ToggleRow({ toggle }: { toggle: Toggle }) {
    const { settings, update } = useSettings()
    const descriptionId = useId()

    return (
        <SettingsRow
            title={toggle.title}
            info={
                toggle.info ? (
                    <InfoTip
                        label={`About ${toggle.title.toLowerCase()}`}
                        descriptionId={descriptionId}
                    >
                        {toggle.info}
                    </InfoTip>
                ) : undefined
            }
        >
            <Switch
                aria-label={toggle.title}
                aria-describedby={toggle.info ? descriptionId : undefined}
                checked={settings[toggle.key]}
                onCheckedChange={(checked) => update({ [toggle.key]: checked })}
            />
        </SettingsRow>
    )
}
