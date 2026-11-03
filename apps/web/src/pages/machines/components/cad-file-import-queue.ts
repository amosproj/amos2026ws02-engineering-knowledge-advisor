import { toast } from '@components'
import type { QueryClient } from '@tanstack/react-query'

import { machinesQueryKey, registerCadFiles, type RegisteredCadFile } from '../query/machine-api'
import { isCancellable, type ImportItem, type ImportPhase } from './cad-file-import-context'
import { CANCELLED, importCadFile, type ImportResult } from './cad-file-import-flow'

const PARALLEL_UPLOADS = 2
const DONE_PHASES: ImportPhase[] = ['ready', 'failed', 'cancelled', 'processing_timeout']

type Job = ImportItem & { cadFile: RegisteredCadFile; file: File; controller: AbortController }

/** Uploads the registered files, PARALLEL_UPLOADS at a time, and follows their processing. */
export function createImportQueue(
    queryClient: QueryClient,
    onChange: (items: ImportItem[]) => void,
) {
    const jobs = new Map<string, Job>()
    const queue: string[] = []
    let running = 0
    let stopped = false

    const render = () =>
        onChange(
            Array.from(
                jobs.values(),
                ({ cadFileId, assemblyGroupId, name, size, phase, percent, message }) => ({
                    cadFileId,
                    assemblyGroupId,
                    name,
                    size,
                    phase,
                    percent,
                    message,
                }),
            ),
        )

    const update = (id: string, changes: Partial<ImportItem>) => {
        const job = jobs.get(id)
        if (!job) return
        Object.assign(job, changes)
        render()
    }

    const refresh = () => void queryClient.invalidateQueries({ queryKey: machinesQueryKey })

    // Slots are taken synchronously, so imports started together never exceed the limit
    const pump = () => {
        while (!stopped && running < PARALLEL_UPLOADS && queue.length > 0) {
            running++
            void run(queue.shift()!, true)
        }
    }

    const run = async (id: string, holdsSlot: boolean) => {
        const job = jobs.get(id)!
        let holding = holdsSlot
        // The slot is freed once the upload is over, not after the processing
        const release = () => {
            if (!holding) return
            holding = false
            running--
            pump()
        }

        if (!job.controller.signal.aborted) update(id, { phase: 'uploading' })
        const result = await importCadFile(job.cadFile, job.file, {
            signal: job.controller.signal,
            onProgress: (percent) => update(id, { percent }),
            onUploaded: () => {
                release()
                update(id, { phase: 'processing', percent: 100 })
                refresh()
            },
        })
        release()
        if (result.status === 'stopped') return

        update(id, {
            phase: result.status,
            message: result.status === 'failed' ? result.message : undefined,
        })
        notify(job.name, result)
        refresh()
        finishIfDone()
    }

    const finishIfDone = () => {
        const done = Array.from(jobs.values())
        if (!done.every((job) => DONE_PHASES.includes(job.phase))) return
        notifySummary(done)
        jobs.clear()
        render()
    }

    const start = async (assemblyGroupId: string, files: File[]) => {
        const registered = await registerCadFiles({
            params: { id: assemblyGroupId },
            body: { files: files.map((file) => ({ filename: file.name, size: file.size })) },
        })
        refresh()
        // The files stay uploading on the server and expire, as for a closed tab
        if (stopped) return

        registered.forEach((cadFile, index) => {
            const file = files[index]
            jobs.set(cadFile.id, {
                cadFileId: cadFile.id,
                assemblyGroupId,
                name: cadFile.name,
                size: file.size,
                phase: 'queued',
                percent: 0,
                cadFile,
                file,
                controller: new AbortController(),
            })
            queue.push(cadFile.id)
        })
        render()
        pump()
    }

    const cancel = (id: string) => {
        const job = jobs.get(id)
        if (!job || !isCancellable(job)) return
        job.controller.abort(CANCELLED)
        const position = queue.indexOf(id)
        // A queued file has no upload to stop, only its registration to delete
        if (position >= 0) {
            queue.splice(position, 1)
            void run(id, false)
        }
    }

    // Unmounting leaves the server state as it is: uploads in progress expire, processing goes on
    const setMounted = (mounted: boolean) => {
        stopped = !mounted
        if (stopped) for (const job of jobs.values()) job.controller.abort()
    }

    return { start, cancel, setMounted }
}

function notify(name: string, result: ImportResult) {
    if (result.status === 'failed') {
        toast.add({
            type: 'error',
            title: `Import of ${name} failed`,
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

function notifySummary(jobs: Job[]) {
    const count = (phase: ImportPhase) => jobs.filter((job) => job.phase === phase).length
    const parts = [
        [count('ready'), 'ready'],
        [count('processing_timeout'), 'still processing'],
        [count('failed'), 'failed'],
        [count('cancelled'), 'cancelled'],
    ]
        .filter(([amount]) => amount)
        .map(([amount, label]) => `${amount} ${label}`)
    toast.add({
        type: count('failed') > 0 ? 'info' : 'success',
        title: 'Import finished',
        description: parts.join(', '),
    })
}
