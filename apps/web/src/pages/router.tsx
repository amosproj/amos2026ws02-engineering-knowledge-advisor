import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, createRoute, createRouter } from '@tanstack/react-router'
import type { RouteBreadcrumb } from '@components'
import { DashboardLayout } from './layout'
import { HomePage } from './home/home-page'
import { MachineBreadcrumb } from './machines/components/machine-breadcrumb'
import { MachineDetailPage } from './machines/machine-detail-page'
import { MachinesPage } from './machines/machines-page'
import { machinesSearchSchema } from './machines/models/machines-search-model'
import { settingsSearchSchema } from './settings/models/settings-model'
import { ImprintPage } from './imprint/imprint-page'
import { ThirdPartyNoticesPage } from './third-party-notices/third-party-notices-page.tsx'
import { PrivacyPolicyPage } from './privacy-policy/privacy-policy-page'
import { SettingsPage } from './settings/settings-page'

interface RouterContext {
    queryClient: QueryClient
}
const rootRoute = createRootRouteWithContext<RouterContext>()({
    component: DashboardLayout,
})

const homeRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    staticData: { breadcrumb: 'Home' },
    component: HomePage,
})

const machinesRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/machines',
    staticData: { breadcrumb: 'Machines' },
})

const machinesIndexRoute = createRoute({
    getParentRoute: () => machinesRoute,
    path: '/',
    validateSearch: machinesSearchSchema,
    component: MachinesPage,
})

const machineDetailRoute = createRoute({
    getParentRoute: () => machinesRoute,
    path: '/$machineId',
    staticData: { breadcrumb: MachineBreadcrumb, sidebarHeader: true },
    component: MachineDetailPage,
})

const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/settings',
    validateSearch: settingsSearchSchema,
    staticData: { breadcrumb: 'Settings' },
    component: SettingsPage,
})

const imprintRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/imprint',
    staticData: { breadcrumb: 'Imprint' },
    component: ImprintPage,
})

const thirdPartyNoticesRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/third-party-notices',
    staticData: { breadcrumb: 'Third-Party Notices' },
    component: ThirdPartyNoticesPage,
})

const privacyPolicyRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/privacy-policy',
    staticData: { breadcrumb: 'Privacy Policy' },
    component: PrivacyPolicyPage,
})

const routeTree = rootRoute.addChildren([
    homeRoute,
    machinesRoute.addChildren([machinesIndexRoute, machineDetailRoute]),
    settingsRoute,
    imprintRoute,
    thirdPartyNoticesRoute,
    privacyPolicyRoute,
])

export const router = createRouter({
    routeTree,
    context: {
        queryClient: undefined!,
    },
})

declare module '@tanstack/react-router' {
    interface Register {
        router: typeof router
    }
    interface StaticDataRouteOption {
        breadcrumb?: RouteBreadcrumb
        /** Header uses the sidebar background in dark mode. */
        sidebarHeader?: boolean
    }
}
