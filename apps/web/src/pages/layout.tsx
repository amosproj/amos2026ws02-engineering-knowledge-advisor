import { Outlet } from '@tanstack/react-router'
import {
    EngineIcon,
    Home02Icon,
    LegalDocument01Icon,
    Settings05Icon,
} from '@hugeicons/core-free-icons'

import { DashboardShell, type DashboardNavConfig } from '@components'

import { ImportIndicator } from './machines/components/import-indicator'

const navConfig: DashboardNavConfig = {
    navMenu: [
        { title: 'Home', link: '/', icon: Home02Icon },
        { title: 'Machines', link: '/machines', icon: EngineIcon },
    ],
    navFooter: [
        {
            title: 'Legal Notices',
            icon: LegalDocument01Icon,
            items: [
                { title: 'Imprint', link: '/imprint' },
                { title: 'Third-Party Notices', link: '/third-party-notices' },
                { title: 'Privacy Policy', link: '/privacy-policy' },
            ],
        },
        { title: 'Settings', link: '/settings', icon: Settings05Icon },
    ],
}

export function DashboardLayout() {
    return (
        <DashboardShell navConfig={navConfig} headerActions={<ImportIndicator />}>
            <Outlet />
        </DashboardShell>
    )
}
