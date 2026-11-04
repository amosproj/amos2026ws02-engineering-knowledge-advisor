import * as React from 'react'
import { Link, useMatches, useRouterState } from '@tanstack/react-router'
import { AiBrain01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import { Separator } from '../atoms'
import {
    Breadcrumb,
    BreadcrumbItem,
    BreadcrumbLink,
    BreadcrumbList,
    BreadcrumbPage,
    BreadcrumbSeparator,
} from '../molecules'
import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    SidebarGroup,
    SidebarHeader,
    SidebarInset,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    SidebarProvider,
    SidebarRail,
    SidebarTrigger,
    useSidebar,
} from '../organisms'

type SidebarLinkTo = NonNullable<React.ComponentProps<typeof Link>['to']>

type SidebarIcon = React.ComponentProps<typeof HugeiconsIcon>['icon']

export type DashboardNavItem = {
    title: string
    link: SidebarLinkTo
    icon: SidebarIcon
}

export type DashboardNavConfig = {
    /** Items rendered at the top of the sidebar. */
    navMenu: readonly DashboardNavItem[]
    /** Items pinned at the bottom of the sidebar. */
    navFooter: readonly DashboardNavItem[]
}

/** Label of a route in the header breadcrumb, set through the route's `staticData.breadcrumb`. */
export type RouteBreadcrumb = string | React.ComponentType<{ params: Record<string, string> }>

type DashboardShellProps = {
    navConfig: DashboardNavConfig
    headerActions?: React.ReactNode
    children?: React.ReactNode
}

const APP_NAME = 'Advisor'

function isActiveLink(link: SidebarLinkTo, pathname: string) {
    return link === '/' ? pathname === '/' : pathname.startsWith(link)
}

function Brand() {
    return (
        <SidebarMenu>
            <SidebarMenuItem>
                <div className="flex h-12 w-full items-center gap-2 overflow-hidden rounded-xl px-3 text-sm font-medium whitespace-nowrap transition-[width,height,padding] duration-200 group-data-[collapsible=icon]:size-8! group-data-[collapsible=icon]:p-0!">
                    <div className="bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 shrink-0 items-center justify-center rounded-lg">
                        <HugeiconsIcon icon={AiBrain01Icon} strokeWidth={2} className="size-4" />
                    </div>
                    <div className="grid flex-1 text-left text-sm leading-tight">
                        <span className="truncate font-medium">{APP_NAME}</span>
                    </div>
                </div>
            </SidebarMenuItem>
        </SidebarMenu>
    )
}

function NavSection({ items, pathname }: { items: readonly DashboardNavItem[]; pathname: string }) {
    return (
        <SidebarMenu>
            {items.map((item) => (
                <SidebarMenuItem key={item.link}>
                    <SidebarMenuButton
                        tooltip={item.title}
                        isActive={isActiveLink(item.link, pathname)}
                        render={<Link to={item.link} />}
                    >
                        <HugeiconsIcon icon={item.icon} strokeWidth={2} />
                        <span>{item.title}</span>
                    </SidebarMenuButton>
                </SidebarMenuItem>
            ))}
        </SidebarMenu>
    )
}

function RouteBreadcrumbs() {
    const crumbs = useMatches({
        select: (matches) =>
            matches.flatMap((match) =>
                match.staticData.breadcrumb
                    ? [
                          {
                              id: match.id,
                              pathname: match.pathname,
                              params: match.params as Record<string, string>,
                              label: match.staticData.breadcrumb,
                          },
                      ]
                    : [],
            ),
    })

    if (crumbs.length === 0) return <span className="truncate text-sm font-medium">{APP_NAME}</span>

    return (
        <Breadcrumb className="min-w-0">
            <BreadcrumbList className="flex-nowrap">
                {crumbs.map(({ id, pathname, params, label: Label }, index) => {
                    const label = typeof Label === 'string' ? Label : <Label params={params} />
                    const isLast = index === crumbs.length - 1
                    return (
                        <React.Fragment key={id}>
                            {index > 0 ? <BreadcrumbSeparator /> : null}
                            <BreadcrumbItem className="min-w-0">
                                {isLast ? (
                                    <BreadcrumbPage className="truncate font-medium">
                                        {label}
                                    </BreadcrumbPage>
                                ) : (
                                    <BreadcrumbLink
                                        className="truncate"
                                        render={<Link to={pathname} />}
                                    >
                                        {label}
                                    </BreadcrumbLink>
                                )}
                            </BreadcrumbItem>
                        </React.Fragment>
                    )
                })}
            </BreadcrumbList>
        </Breadcrumb>
    )
}

function CloseMobileSidebarOnNavigate({ pathname }: { pathname: string }) {
    const { setOpenMobile } = useSidebar()

    React.useEffect(() => {
        setOpenMobile(false)
    }, [pathname, setOpenMobile])

    return null
}

export function DashboardShell({ navConfig, headerActions, children }: DashboardShellProps) {
    const pathname = useRouterState({ select: (state) => state.location.pathname })

    return (
        <SidebarProvider>
            <CloseMobileSidebarOnNavigate pathname={pathname} />
            <Sidebar collapsible="icon">
                <SidebarHeader>
                    <Brand />
                </SidebarHeader>
                <SidebarContent>
                    <SidebarGroup>
                        <NavSection items={navConfig.navMenu} pathname={pathname} />
                    </SidebarGroup>
                </SidebarContent>
                <SidebarFooter>
                    <NavSection items={navConfig.navFooter} pathname={pathname} />
                </SidebarFooter>
                <SidebarRail />
            </Sidebar>
            <SidebarInset className="min-w-0">
                <header className="flex h-16 shrink-0 items-center justify-between gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
                    <div className="flex min-w-0 items-center gap-2 px-4">
                        <SidebarTrigger className="-ml-1" />
                        <Separator
                            orientation="vertical"
                            className="mr-2 data-vertical:h-4 data-vertical:self-auto"
                        />
                        <RouteBreadcrumbs />
                    </div>
                    {headerActions ? (
                        <div className="flex shrink-0 items-center gap-2 px-4">{headerActions}</div>
                    ) : null}
                </header>
                <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-4 pt-0">
                    {children}
                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
