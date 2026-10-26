import { Button, ConfirmationPopup } from '@components'

import { SettingsRow, SettingsSection } from './settings-layout'

export function ResetSettings({ onConfirm }: { onConfirm: () => void }) {
    return (
        <SettingsSection title="Reset">
            <SettingsRow
                title="Restore defaults"
                description="Return every application setting, including the theme, to its default value."
            >
                <ConfirmationPopup
                    title="Restore default settings?"
                    description="Every application setting will return to its default value. This cannot be undone."
                    confirmLabel="Reset"
                    onConfirm={onConfirm}
                >
                    <Button type="button" variant="secondary">
                        Reset
                    </Button>
                </ConfirmationPopup>
            </SettingsRow>
        </SettingsSection>
    )
}
