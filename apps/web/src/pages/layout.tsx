import { Link, Outlet } from '@tanstack/react-router'
import { EngineIcon, Home02Icon, Settings05Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Button,
    DashboardShell,
    Tooltip,
    TooltipContent,
    TooltipTrigger,
    type DashboardNavConfig,
} from '@components'

import { ImportIndicator } from './machines/components/import-indicator'

const navConfig: DashboardNavConfig = {
    navMenu: [
        { title: 'Home', link: '/', icon: Home02Icon },
        { title: 'Machines', link: '/machines', icon: EngineIcon },
    ],
    navFooter: [{ title: 'Settings', link: '/settings', icon: Settings05Icon }],
}

function HeaderActions() {
    return (
        <>
            <ImportIndicator />
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
