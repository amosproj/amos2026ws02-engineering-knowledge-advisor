import * as React from 'react'
import { Link, useRouterState } from '@tanstack/react-router'
import { AiBrain01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import { Separator } from '../atoms'
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

type DashboardShellProps = {
    navConfig: DashboardNavConfig
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

export function DashboardShell({ navConfig, children }: DashboardShellProps) {
    const pathname = useRouterState({ select: (state) => state.location.pathname })

    const activeTitle = [...navConfig.navMenu, ...navConfig.navFooter].find((item) =>
        isActiveLink(item.link, pathname),
    )?.title

    return (
        <SidebarProvider>
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
            <SidebarInset>
                <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
                    <div className="flex items-center gap-2 px-4">
                        <SidebarTrigger className="-ml-1" />
                        <Separator
                            orientation="vertical"
                            className="mr-2 data-vertical:h-4 data-vertical:self-auto"
                        />
                        <span className="text-sm font-medium">{activeTitle ?? APP_NAME}</span>
                    </div>
                </header>
                <div className="flex flex-1 flex-col gap-6 overflow-y-auto p-4 pt-0">
                    {children}
                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
