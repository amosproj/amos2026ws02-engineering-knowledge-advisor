import { useId } from 'react'

import { InfoTip, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@components'
import { SettingsRow, SettingsSection } from '@pages/settings/components/settings-layout'

import { upAxis, type UpAxis } from '../query/machine-api'

const axisItems = upAxis.options.map((axis) => ({ value: axis, label: axis.replace('-', '−') }))

type UpAxisSettingsProps = {
    value: UpAxis
    disabled: boolean
    onChange: (axis: UpAxis) => void
}

export function UpAxisSettings({ value, disabled, onChange }: UpAxisSettingsProps) {
    const descriptionId = useId()

    return (
        <SettingsSection title="Model">
            <SettingsRow
                title="Up axis"
                info={
                    <InfoTip label="About up axis" descriptionId={descriptionId}>
                        Axis of the CAD file that points up. Change it if the model lies on its
                        side. Saved for this machine, for all users.
                    </InfoTip>
                }
            >
                <Select
                    items={axisItems}
                    value={value}
                    disabled={disabled}
                    onValueChange={(axis) => {
                        if (axis && axis !== value) onChange(axis)
                    }}
                >
                    <SelectTrigger
                        className="w-20"
                        aria-label="Up axis"
                        aria-describedby={descriptionId}
                    >
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        {axisItems.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                                {item.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </SettingsRow>
        </SettingsSection>
    )
}
