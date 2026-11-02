import { Link, Outlet } from '@tanstack/react-router'
import { Home02Icon, Settings05Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Button,
    DashboardShell,
    ImportMachineDialog,
    Tooltip,
    TooltipContent,
    TooltipTrigger,
    toast,
    type DashboardNavConfig,
} from '@components'
import type { MachineImport } from '@components/atomic/organisms/machine-import/import-machine-model'

const navConfig: DashboardNavConfig = {
    navMenu: [{ title: 'Home', link: '/', icon: Home02Icon }],
    navFooter: [{ title: 'Settings', link: '/settings', icon: Settings05Icon }],
}

async function submitMachineImport(machineImport: MachineImport) {
    console.log('Machine import submitted:', machineImport)
    //TODO: Implement the actual submission logic for machine import
    toast.add({
        type: 'info',
        title: 'Upload not connected yet',
        description: 'The file was not sent.',
    })
}

function HeaderActions() {
    return (
        <>
            <ImportMachineDialog onSubmit={submitMachineImport} />
            <Tooltip>
                <TooltipTrigger
                    render={
                        <Button
                            variant="secondary"
                            size="icon"
                            aria-label="Settings"
                            nativeButton={false}
                            render={<Link to="/settings" />}
                        />
                    }
                >
                    <HugeiconsIcon icon={Settings05Icon} strokeWidth={2} />
                </TooltipTrigger>
                <TooltipContent side="bottom">Settings</TooltipContent>
            </Tooltip>
        </>
    )
}

export function DashboardLayout() {
    return (
        <DashboardShell navConfig={navConfig} headerActions={<HeaderActions />}>
            <Outlet />
        </DashboardShell>
    )
}
