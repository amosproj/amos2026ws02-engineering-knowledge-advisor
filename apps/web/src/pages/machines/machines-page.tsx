import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Add01Icon, EngineIcon, Search01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Button,
    Empty,
    EmptyContent,
    EmptyDescription,
    EmptyHeader,
    EmptyMedia,
    EmptyTitle,
    InputGroup,
    InputGroupAddon,
    InputGroupInput,
} from '@components'

import { MachineFormDialog } from './components/machine-form-dialog'
import { MachinesPagination } from './components/machines-pagination'
import { MachinesTable } from './components/machines-table'
import { MACHINES_PER_PAGE } from './models/machines-search-model'
import { machinesQuery, type Machine } from './query/machine-api'

const POLL_MS = 3_000

export function MachinesPage() {
    const search = useSearch({ from: '/machines/' })
    const navigate = useNavigate({ from: '/machines/' })

    const {
        data: machines,
        isError,
        isFetching,
        refetch,
    } = useQuery({
        ...machinesQuery,
        refetchOnWindowFocus: true,
        refetchInterval: (query) => (query.state.data?.some(isBusy) ? POLL_MS : false),
    })

    const query = search.q?.trim().toLowerCase() ?? ''
    const found = machines?.filter((machine) => matches(machine, query))
    const pageCount = Math.max(1, Math.ceil((found?.length ?? 0) / MACHINES_PER_PAGE))
    const page = Math.min(search.page ?? 1, pageCount)
    const pageMachines = found?.slice((page - 1) * MACHINES_PER_PAGE, page * MACHINES_PER_PAGE)

    // Once the list is up to date, drop a page past the end
    useEffect(() => {
        if (!machines || isFetching) return
        const pageParam = page > 1 ? page : undefined
        if (pageParam !== search.page) {
            void navigate({ search: (prev) => ({ ...prev, page: pageParam }), replace: true })
        }
    }, [machines, isFetching, page, search.page, navigate])

    const openMachine = (machineId: string) =>
        void navigate({ to: '/machines/$machineId', params: { machineId } })

    const newMachineButton = (
        <Button>
            <HugeiconsIcon icon={Add01Icon} strokeWidth={2} data-icon="inline-start" />
            New machine
        </Button>
    )

    return (
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-2 py-6 md:py-10">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <h1 className="font-heading text-2xl font-semibold tracking-tight">Machines</h1>
                </div>
                <MachineFormDialog
                    trigger={newMachineButton}
                    onCreated={(machine) => openMachine(machine.id)}
                />
            </div>

            {isError && !machines ? (
                <Empty className="border">
                    <EmptyHeader>
                        <EmptyTitle>The machines could not be loaded</EmptyTitle>
                        <EmptyDescription>Check your connection and try again.</EmptyDescription>
                    </EmptyHeader>
                    <EmptyContent>
                        <Button variant="outline" onClick={() => void refetch()}>
                            Try again
                        </Button>
                    </EmptyContent>
                </Empty>
            ) : machines?.length === 0 ? (
                <Empty className="border">
                    <EmptyHeader>
                        <EmptyMedia variant="icon">
                            <HugeiconsIcon icon={EngineIcon} strokeWidth={2} />
                        </EmptyMedia>
                        <EmptyTitle>No machines yet</EmptyTitle>
                        <EmptyDescription>
                            Create a machine, then import the STEP files of its assembly groups.
                        </EmptyDescription>
                    </EmptyHeader>
                </Empty>
            ) : (
                <>
                    <InputGroup className="max-w-sm">
                        <InputGroupAddon>
                            <HugeiconsIcon icon={Search01Icon} strokeWidth={2} />
                        </InputGroupAddon>
                        <InputGroupInput
                            type="search"
                            placeholder="Search by name, identifier or customer"
                            aria-label="Search machines"
                            value={search.q ?? ''}
                            onChange={(event) =>
                                void navigate({
                                    search: { q: event.target.value || undefined },
                                    replace: true,
                                })
                            }
                        />
                    </InputGroup>
                    {found?.length === 0 ? (
                        <p className="text-muted-foreground text-sm">No machine matches.</p>
                    ) : (
                        <>
                            <MachinesTable machines={pageMachines} onOpen={openMachine} />
                            <MachinesPagination page={page} pageCount={pageCount} />
                        </>
                    )}
                </>
            )}
        </div>
    )
}

function isBusy(machine: Machine) {
    return machine.status === 'uploading' || machine.status === 'processing'
}

function matches(machine: Machine, query: string) {
    return [machine.name, machine.identifier, machine.customer].some((text) =>
        text?.toLowerCase().includes(query),
    )
}
