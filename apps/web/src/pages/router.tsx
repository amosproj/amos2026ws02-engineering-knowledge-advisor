import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, createRoute, createRouter } from '@tanstack/react-router'
import type { RouteBreadcrumb } from '@components'
import { DashboardLayout } from './layout'
import { HomePage } from './home/home-page'
import { MachineBreadcrumb } from './machines/components/machine-breadcrumb'
import { MachineDetailPage } from './machines/machine-detail-page'
import { MachinesPage } from './machines/machines-page'
import { machinesSearchSchema } from './machines/models/machines-search-model'
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
    path: '$machineId',
    staticData: { breadcrumb: MachineBreadcrumb },
    component: MachineDetailPage,
})

const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/settings',
    staticData: { breadcrumb: 'Settings' },
    component: SettingsPage,
})

const routeTree = rootRoute.addChildren([
    homeRoute,
    machinesRoute.addChildren([machinesIndexRoute, machineDetailRoute]),
    settingsRoute,
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
    }
}
