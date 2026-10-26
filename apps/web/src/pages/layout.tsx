import { Outlet } from '@tanstack/react-router'
import { Home02Icon, Settings05Icon } from '@hugeicons/core-free-icons'

import { DashboardShell, type DashboardNavConfig } from '@components'

const navConfig: DashboardNavConfig = {
    navMenu: [{ title: 'Home', link: '/', icon: Home02Icon }],
    navFooter: [{ title: 'Settings', link: '/settings', icon: Settings05Icon }],
}

export function DashboardLayout() {
    return (
        <DashboardShell navConfig={navConfig}>
            <Outlet />
        </DashboardShell>
    )
}
