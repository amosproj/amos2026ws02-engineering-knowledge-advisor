import { Home09Icon, Settings05Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import { Button, Dialog, DialogContent, DialogHeader, DialogTitle } from '@components'
import { ViewerSettings } from '@pages/settings/components/viewer-settings'

type ViewerToolbarProps = {
    settingsOpen: boolean
    onSettingsOpenChange: (open: boolean) => void
    onReset: () => void
}

export function ViewerToolbar({ settingsOpen, onSettingsOpenChange, onReset }: ViewerToolbarProps) {
    return (
        <>
            <Button
                variant="ghost"
                size="icon"
                aria-label="Viewer settings"
                title="Viewer settings"
                className="text-muted-foreground absolute"
                style={{ right: 15, bottom: 150 }}
                onClick={() => onSettingsOpenChange(true)}
            >
                <HugeiconsIcon icon={Settings05Icon} strokeWidth={1.5} className="size-5" />
            </Button>
            <Dialog open={settingsOpen} onOpenChange={onSettingsOpenChange}>
                <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg md:max-w-4xl">
                    <DialogHeader>
                        <DialogTitle>3D viewer settings</DialogTitle>
                    </DialogHeader>
                    <ViewerSettings columns />
                </DialogContent>
            </Dialog>
            <Button
                variant="ghost"
                size="icon"
                aria-label="Reset view"
                title="Reset view"
                className="text-muted-foreground absolute"
                style={{ right: 15, bottom: 110 }}
                onClick={onReset}
            >
                <HugeiconsIcon icon={Home09Icon} strokeWidth={1.5} className="size-5" />
            </Button>
        </>
    )
}
