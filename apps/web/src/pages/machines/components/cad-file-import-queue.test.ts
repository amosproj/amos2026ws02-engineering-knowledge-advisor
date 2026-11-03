import { QueryClient } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { toast } from '@components'
import { registerCadFiles } from '../query/machine-api'
import type { ImportItem } from './cad-file-import-context'
import { CANCELLED, importCadFile, type ImportResult } from './cad-file-import-flow'
import { createImportQueue } from './cad-file-import-queue'

vi.mock('@components', () => ({ toast: { add: vi.fn() } }))
vi.mock('../query/machine-api', () => ({
    machinesQueryKey: ['machines'],
    registerCadFiles: vi.fn(),
}))
vi.mock('./cad-file-import-flow', () => ({ CANCELLED: 'cancelled', importCadFile: vi.fn() }))

type Run = {
    signal: AbortSignal
    uploaded: () => void
    finish: (result: ImportResult) => void
}

/** Every call of importCadFile, to be driven by the test. */
function fakeImports() {
    const runs = new Map<string, Run>()
    vi.mocked(importCadFile).mockImplementation(
        (cadFile, _file, { signal, onUploaded }) =>
            new Promise((resolve) => {
                runs.set(cadFile.id, { signal, uploaded: onUploaded, finish: resolve })
            }),
    )
    return runs
}

function registered(...ids: string[]) {
    vi.mocked(registerCadFiles).mockResolvedValueOnce(
        ids.map((id) => ({ id, name: `${id}.step`, upload: { url: '/storage', fields: {} } })),
    )
    return ids.map((id) => new File(['x'], `${id}.step`))
}

function setup() {
    let items: ImportItem[] = []
    const queue = createImportQueue(new QueryClient(), (next) => (items = next))
    queue.setMounted(true)
    return {
        queue,
        items: () => items,
        phase: (id: string) => items.find((item) => item.cadFileId === id)?.phase,
    }
}

afterEach(() => {
    vi.resetAllMocks()
})

describe('createImportQueue', () => {
    it('uploads two files at a time and frees a slot as soon as an upload is over', async () => {
        const runs = fakeImports()
        const { queue, phase } = setup()

        await queue.start('ag-1', registered('a', 'b', 'c'))

        expect([...runs.keys()]).toEqual(['a', 'b'])
        expect(phase('c')).toBe('queued')
        runs.get('a')!.uploaded()
        expect([...runs.keys()]).toEqual(['a', 'b', 'c'])
        expect(phase('a')).toBe('processing')
    })

    it('never runs more than two uploads for imports started together', async () => {
        const runs = fakeImports()
        const { queue } = setup()

        await Promise.all([
            queue.start('ag-1', registered('a', 'b')),
            queue.start('ag-2', registered('c')),
        ])

        expect(runs.size).toBe(2)
    })

    it('deletes a cancelled queued file without waiting for a slot', async () => {
        const runs = fakeImports()
        const { queue } = setup()
        await queue.start('ag-1', registered('a', 'b', 'c'))

        queue.cancel('c')

        expect(runs.get('c')!.signal.reason).toBe(CANCELLED)
        runs.get('a')!.uploaded()
        // c is no longer in the queue, so no upload starts for it again
        expect(
            vi.mocked(importCadFile).mock.calls.filter(([file]) => file.id === 'c'),
        ).toHaveLength(1)
    })

    it('notifies the failures and a summary, then clears the list', async () => {
        const runs = fakeImports()
        const { queue, items } = setup()
        await queue.start('ag-1', registered('a', 'b'))

        runs.get('a')!.finish({ status: 'ready' })
        runs.get('b')!.finish({
            status: 'failed',
            message: 'This STEP file has already been imported.',
        })
        await vi.waitFor(() => expect(items()).toEqual([]))

        const toasts = vi.mocked(toast.add).mock.calls.map(([options]) => options)
        expect(toasts).toEqual([
            expect.objectContaining({
                type: 'error',
                description: 'This STEP file has already been imported.',
            }),
            expect.objectContaining({ title: 'Import finished', description: '1 ready, 1 failed' }),
        ])
    })

    it('stops following the files when unmounted and ignores a late registration', async () => {
        const runs = fakeImports()
        const { queue, items } = setup()
        await queue.start('ag-1', registered('a'))
        const late = queue.start('ag-1', registered('b'))

        queue.setMounted(false)
        await late

        expect(runs.get('a')!.signal.aborted).toBe(true)
        expect(runs.get('a')!.signal.reason).not.toBe(CANCELLED)
        expect(runs.has('b')).toBe(false)
        expect(items().map((item) => item.cadFileId)).toEqual(['a'])
    })
})
