import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Factory01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Button,
    Empty,
    EmptyContent,
    EmptyDescription,
    EmptyHeader,
    EmptyMedia,
    EmptyTitle,
} from '@components'

import { ImportMachineDialog } from './components/import-machine-dialog'
import { useMachineImport } from './components/machine-import-context'
import { MachineDrawer } from './components/machine-drawer'
import { MachinesPagination } from './components/machines-pagination'
import { MachinesTable } from './components/machines-table'
import { MACHINES_PER_PAGE } from './models/machines-search-model'
import { machinesQuery } from './query/machine-api'

const PROCESSING_POLL_MS = 3_000

export function MachinesPage() {
    const search = useSearch({ from: '/machines' })
    const navigate = useNavigate({ from: '/machines' })
    const { activeImport } = useMachineImport()

    const {
        data: machines,
        isError,
        isFetching,
        refetch,
    } = useQuery({
        ...machinesQuery,
        refetchOnWindowFocus: true,
        // The import running in this tab already follows its own machine
        refetchInterval: (query) =>
            query.state.data?.some(
                (machine) =>
                    machine.status === 'processing' && machine.id !== activeImport?.machineId,
            )
                ? PROCESSING_POLL_MS
                : false,
    })

    const pageCount = Math.max(1, Math.ceil((machines?.length ?? 0) / MACHINES_PER_PAGE))
    const page = Math.min(search.page ?? 1, pageCount)
    const pageMachines = machines?.slice((page - 1) * MACHINES_PER_PAGE, page * MACHINES_PER_PAGE)
    const openMachine = machines?.find((machine) => machine.id === search.machine)

    // Keeps the drawer content while its closing animation plays
    const [shownMachine, setShownMachine] = useState(openMachine)
    if (openMachine && openMachine !== shownMachine) setShownMachine(openMachine)

    // Once the list is up to date, drop a page past the end or a machine that no longer exists
    useEffect(() => {
        if (!machines || isFetching) return
        const pageParam = page > 1 ? page : undefined
        if (pageParam !== search.page || openMachine?.id !== search.machine) {
            void navigate({
                search: { page: pageParam, machine: openMachine?.id },
                replace: true,
            })
        }
    }, [machines, isFetching, page, openMachine, search.page, search.machine, navigate])

    const setOpenMachine = (machineId: string | undefined) =>
        void navigate({ search: (prev) => ({ ...prev, machine: machineId }) })

    return (
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-2 py-6 md:py-10">
            <div>
                <h1 className="font-heading text-2xl font-semibold tracking-tight">Machines</h1>
                <p className="text-muted-foreground text-sm">
                    Imported machines and the state of their STEP file.
                </p>
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
                            <HugeiconsIcon icon={Factory01Icon} strokeWidth={2} />
                        </EmptyMedia>
                        <EmptyTitle>No machines yet</EmptyTitle>
                        <EmptyDescription>
                            Import the STEP file of a machine to add it here.
                        </EmptyDescription>
                    </EmptyHeader>
                    <EmptyContent>
                        <ImportMachineDialog />
                    </EmptyContent>
                </Empty>
            ) : (
                <>
                    <MachinesTable machines={pageMachines} onOpen={setOpenMachine} />
                    <MachinesPagination page={page} pageCount={pageCount} />
                </>
            )}

            <MachineDrawer
                machine={shownMachine}
                open={!!openMachine}
                onClose={() => setOpenMachine(undefined)}
            />
        </div>
    )
}
