import type { QueryClient } from '@tanstack/react-query'
import { createRootRouteWithContext, createRoute, createRouter } from '@tanstack/react-router'
import { DashboardLayout } from './layout'
import { HomePage } from './home/home-page'
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
    component: HomePage,
})

const machinesRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/machines',
    validateSearch: machinesSearchSchema,
    component: MachinesPage,
})

const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/settings',
    component: SettingsPage,
})

const routeTree = rootRoute.addChildren([homeRoute, machinesRoute, settingsRoute])

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
}
