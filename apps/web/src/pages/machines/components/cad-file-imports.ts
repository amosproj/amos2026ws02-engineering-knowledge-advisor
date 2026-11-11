import { toast } from '@components'
import type { QueryClient } from '@tanstack/react-query'

import { HttpError } from '@queries/query-errors'

import { createCadFile, deleteRecord, machinesQueryKey, updateCadFile } from '../query/machine-api'
import type { ImportItem, ImportTarget } from './cad-file-import-context'
import { CANCELLED, importCadFile, type ImportResult } from './cad-file-import-flow'

type Job = ImportItem & { controller: AbortController }

export function createImports(queryClient: QueryClient, onChange: (items: ImportItem[]) => void) {
    const jobs = new Map<string, Job>()
    const starting = new Set<string>()
    let stopped = false

    const render = () =>
        onChange(
            Array.from(jobs.values(), ({ machineId, cadFileId, name, size, phase, percent }) => ({
                machineId,
                cadFileId,
                name,
                size,
                phase,
                percent,
            })),
        )

    const update = (machineId: string, changes: Partial<ImportItem>) => {
        const job = jobs.get(machineId)
        if (!job) return
        Object.assign(job, changes)
        render()
    }

    const refresh = () => void queryClient.invalidateQueries({ queryKey: machinesQueryKey })

    const start = async (target: ImportTarget) => {
        const { machineId, file } = target
        if (jobs.has(machineId) || starting.has(machineId)) {
            throw new Error('A file of this machine is uploading already.')
        }
        starting.add(machineId)
        let cadFileId: string
        try {
            cadFileId = await register(target)
        } finally {
            starting.delete(machineId)
            refresh()
        }
        if (stopped) return

        const job: Job = {
            machineId,
            cadFileId,
            name: file.name,
            size: file.size,
            phase: 'uploading',
            percent: 0,
            controller: new AbortController(),
        }
        jobs.set(machineId, job)
        render()
        void run(job, file)
    }

    const run = async (job: Job, file: File) => {
        const result = await importCadFile(job.cadFileId, file, {
            signal: job.controller.signal,
            onProgress: (percent) => update(job.machineId, { percent }),
            onUploaded: () => {
                update(job.machineId, { phase: 'processing', percent: 100 })
                refresh()
            },
        })
        jobs.delete(job.machineId)
        render()
        refresh()
        notify(job.name, result)
    }

    const cancel = (machineId: string) => {
        const job = jobs.get(machineId)
        if (job?.phase === 'uploading') job.controller.abort(CANCELLED)
    }

    const setMounted = (mounted: boolean) => {
        stopped = !mounted
        if (stopped) for (const job of jobs.values()) job.controller.abort()
    }

    return { start, cancel, setMounted }
}

async function register({ machineId, file, reuseId, replaceId }: ImportTarget) {
    const details = { name: file.name, timestamp: new Date(file.lastModified).toISOString() }
    if (reuseId) {
        await updateCadFile({ params: { id: reuseId }, body: details })
        return reuseId
    }
    if (replaceId) {
        try {
            await deleteRecord({ params: { id: replaceId } })
        } catch (error) {
            // Deleted by an earlier attempt whose new record could not be created
            if (!(error instanceof HttpError && error._tag === 'NotFound')) throw error
        }
    }
    const created = await createCadFile({
        body: { '@type': 'CadFile', ...details, format: 'STEP', partOf: machineId },
    })
    return created.id
}

function notify(name: string, result: ImportResult) {
    if (result.status === 'ready') {
        toast.add({ type: 'success', title: `${name} is ready` })
    } else if (result.status === 'failed') {
        toast.add({
            type: 'error',
            title: `Upload of ${name} failed`,
            description: result.message,
            timeout: 0,
        })
    } else if (result.status === 'processing_timeout') {
        toast.add({
            type: 'info',
            title: `${name} is taking longer than expected`,
            description: 'Its processing continues on the server.',
        })
    }
}
