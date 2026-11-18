import { Outlet } from '@tanstack/react-router'
import { EngineIcon, Home02Icon, Settings05Icon } from '@hugeicons/core-free-icons'

import { DashboardShell, type DashboardNavConfig } from '@components'

import { ImportIndicator } from './machines/components/import-indicator'

const navConfig: DashboardNavConfig = {
    navMenu: [
        { title: 'Home', link: '/', icon: Home02Icon },
        { title: 'Machines', link: '/machines', icon: EngineIcon },
    ],
    navFooter: [{ title: 'Settings', link: '/settings', icon: Settings05Icon }],
}

export function DashboardLayout() {
    return (
        <DashboardShell navConfig={navConfig} headerActions={<ImportIndicator />}>
            <Outlet />
        </DashboardShell>
    )
}
