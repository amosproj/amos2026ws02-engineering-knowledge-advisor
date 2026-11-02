import { useLinkProps } from '@tanstack/react-router'
import { cn } from 'cn'

import {
    Pagination,
    PaginationContent,
    PaginationEllipsis,
    PaginationItem,
    PaginationLink,
    PaginationNext,
    PaginationPrevious,
} from '@components'

type MachinesPaginationProps = {
    page: number
    pageCount: number
}

export function MachinesPagination({ page, pageCount }: MachinesPaginationProps) {
    if (pageCount <= 1) return null

    return (
        <Pagination>
            <PaginationContent>
                <PaginationItem>
                    <PageLink page={page - 1} kind="previous" disabled={page === 1} />
                </PaginationItem>
                {pageItems(page, pageCount).map((item, index) => (
                    <PaginationItem key={index}>
                        {item === 'ellipsis' ? (
                            <PaginationEllipsis />
                        ) : (
                            <PageLink page={item} isActive={item === page}>
                                {item}
                            </PageLink>
                        )}
                    </PaginationItem>
                ))}
                <PaginationItem>
                    <PageLink page={page + 1} kind="next" disabled={page === pageCount} />
                </PaginationItem>
            </PaginationContent>
        </Pagination>
    )
}

type PageLinkProps = {
    page: number
    kind?: 'previous' | 'next'
    isActive?: boolean
    disabled?: boolean
    children?: React.ReactNode
}

function PageLink({ page, kind, isActive, disabled, children }: PageLinkProps) {
    const linkProps = useLinkProps({
        from: '/machines',
        to: '/machines',
        search: { page: page > 1 ? page : undefined },
        // Without this, every link to /machines is marked as the current page
        activeOptions: { exact: true, includeSearch: true },
        disabled,
    })
    const Link =
        kind === 'previous' ? PaginationPrevious : kind === 'next' ? PaginationNext : PaginationLink

    return (
        <Link
            {...linkProps}
            isActive={isActive}
            aria-disabled={disabled}
            tabIndex={disabled ? -1 : undefined}
            className={cn(disabled && 'pointer-events-none opacity-50')}
        >
            {children}
        </Link>
    )
}

/** First page, last page and the pages around the current one, with gaps in between. */
function pageItems(page: number, pageCount: number): (number | 'ellipsis')[] {
    const pages = [1, page - 1, page, page + 1, pageCount].filter(
        (item, index, all) => item >= 1 && item <= pageCount && all.indexOf(item) === index,
    )
    return pages.flatMap((item, index) =>
        index > 0 && item - pages[index - 1] > 1 ? ['ellipsis' as const, item] : [item],
    )
}
