import { toast } from '@components'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useRef, useState, useMemo, useEffect } from 'react'

import type { MachineImport } from '../models/import-machine-model'
import {
    createMachine,
    machinesQueryKey,
    type Machine,
    type MachineStatus,
} from '../query/machine-api'
import { MachineImportContext, type ActiveImport, type ImportPhase } from './machine-import-context'
import { followMachineImport, type ImportResult } from './machine-import-flow'

export function MachineImportProvider({ children }: { children: React.ReactNode }) {
    const queryClient = useQueryClient()
    const [activeImport, setActiveImport] = useState<ActiveImport | null>(null)
    const runRef = useRef<{ controller: AbortController; phase: ImportPhase } | null>(null)

    const startImport = useCallback(
        async (machineImport: MachineImport) => {
            if (runRef.current) throw new Error('An import is already in progress.')

            const run = { controller: new AbortController(), phase: 'uploading' as ImportPhase }
            runRef.current = run
            const { machineName: name, machineDescription, file } = machineImport
            const description = machineDescription || undefined

            let machine: Awaited<ReturnType<typeof createMachine>>
            try {
                machine = await createMachine({
                    body: { name, description, filename: file.name, size: file.size },
                })
            } catch (error) {
                runRef.current = null
                throw error
            }

            setActiveImport({
                machineId: machine.id,
                name,
                description,
                file,
                phase: 'uploading',
                percent: 0,
            })
            void queryClient.invalidateQueries({ queryKey: machinesQueryKey })
            void followMachineImport(machine, file, {
                signal: run.controller.signal,
                onProgress: (percent) =>
                    setActiveImport((current) => current && { ...current, percent }),
                onProcessing: () => {
                    run.phase = 'processing'
                    setActiveImport((current) => current && { ...current, phase: 'processing' })
                },
            }).then((result) => {
                notify(name, result)
                // The list takes over the row: it must not fall back to an older status meanwhile
                queryClient.setQueryData<Machine[]>(machinesQueryKey, (machines) =>
                    settleMachine(machines, machine.id, result),
                )
                runRef.current = null
                setActiveImport(null)
                void queryClient.invalidateQueries({ queryKey: machinesQueryKey })
            })
        },
        [queryClient],
    )

    const cancelImport = useCallback(() => {
        if (runRef.current?.phase === 'uploading') runRef.current.controller.abort()
    }, [])

    // Prevent the user from closing the page while an import is in progress.
    const isUploading = activeImport?.phase === 'uploading'
    useEffect(() => {
        if (!isUploading) return
        const warn = (event: BeforeUnloadEvent) => event.preventDefault()
        window.addEventListener('beforeunload', warn)
        return () => window.removeEventListener('beforeunload', warn)
    }, [isUploading])

    const value = useMemo(
        () => ({ activeImport, startImport, cancelImport }),
        [activeImport, startImport, cancelImport],
    )

    return <MachineImportContext.Provider value={value}>{children}</MachineImportContext.Provider>
}

/** Apply what the import knows about its machine, a failure is left to the refetch. */
function settleMachine(
    machines: Machine[] | undefined,
    machineId: string,
    result: ImportResult,
): Machine[] | undefined {
    if (result.status === 'failed') return machines
    if (result.status === 'cancelled') return machines?.filter((item) => item.id !== machineId)
    const status: MachineStatus = result.status === 'ready' ? 'ready' : 'processing'
    return machines?.map((item) => (item.id === machineId ? { ...item, status } : item))
}

function notify(name: string, result: ImportResult) {
    if (result.status === 'ready') {
        toast.add({ type: 'success', title: 'Machine imported', description: `${name} is ready.` })
    } else if (result.status === 'cancelled') {
        toast.add({ type: 'info', title: 'Import cancelled', description: name })
    } else if (result.status === 'processing_timeout') {
        toast.add({
            type: 'info',
            title: `Import of ${name} is taking longer than expected`,
            description: 'It continues on the server.',
        })
    } else {
        toast.add({
            type: 'error',
            title: `Import of ${name} failed`,
            description: result.message,
            timeout: 0,
        })
    }
}
