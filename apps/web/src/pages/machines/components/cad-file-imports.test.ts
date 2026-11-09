import { QueryClient } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { toast } from '@components'
import { HttpError } from '@queries/query-errors'
import { createCadFile, deleteRecord, updateCadFile } from '../query/machine-api'
import type { ImportItem } from './cad-file-import-context'
import { CANCELLED, importCadFile, type ImportResult } from './cad-file-import-flow'
import { createImports } from './cad-file-imports'

vi.mock('@components', () => ({ toast: { add: vi.fn() } }))
vi.mock('../query/machine-api', () => ({
    machinesQueryKey: ['machines'],
    createCadFile: vi.fn(),
    deleteRecord: vi.fn(),
    updateCadFile: vi.fn(),
}))
vi.mock('./cad-file-import-flow', () => ({ CANCELLED: 'cancelled', importCadFile: vi.fn() }))

const file = new File(['x'], 'cell.step', { lastModified: Date.UTC(2026, 10, 8) })
const written = { id: 'cad-new', warnings: [], version: '1' }

type Run = {
    signal: AbortSignal
    uploaded: () => void
    finish: (result: ImportResult) => void
}

/** Every call of importCadFile, to be driven by the test. */
function fakeImports() {
    const runs = new Map<string, Run>()
    vi.mocked(importCadFile).mockImplementation(
        (cadFileId, _file, { signal, onUploaded }) =>
            new Promise((resolve) => {
                runs.set(cadFileId, { signal, uploaded: onUploaded, finish: resolve })
            }),
    )
    return runs
}

function setup() {
    let items: ImportItem[] = []
    const imports = createImports(new QueryClient(), (next) => (items = next))
    imports.setMounted(true)
    return { imports, items: () => items }
}

afterEach(() => {
    vi.resetAllMocks()
})

describe('createImports', () => {
    it('creates the CAD file record of the machine and follows its upload', async () => {
        const runs = fakeImports()
        vi.mocked(createCadFile).mockResolvedValue(written)
        const { imports, items } = setup()

        await imports.start({ machineId: 'm-1', file })

        expect(createCadFile).toHaveBeenCalledWith({
            body: {
                '@type': 'CadFile',
                name: 'cell.step',
                timestamp: '2026-11-08T00:00:00.000Z',
                format: 'STEP',
                partOf: 'm-1',
            },
        })
        expect(items()).toEqual([
            {
                machineId: 'm-1',
                cadFileId: 'cad-new',
                name: 'cell.step',
                size: 1,
                phase: 'uploading',
                percent: 0,
            },
        ])
        runs.get('cad-new')!.uploaded()
        expect(items()[0].phase).toBe('processing')
        runs.get('cad-new')!.finish({ status: 'ready' })
        await vi.waitFor(() => expect(items()).toEqual([]))
        expect(toast.add).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' }))
    })

    it('reuses a CAD file record with the new file name', async () => {
        fakeImports()
        const { imports } = setup()

        await imports.start({ machineId: 'm-1', file, reuseId: 'cad-1' })

        expect(updateCadFile).toHaveBeenCalledWith({
            params: { id: 'cad-1' },
            body: { name: 'cell.step', timestamp: '2026-11-08T00:00:00.000Z' },
        })
        expect(createCadFile).not.toHaveBeenCalled()
        expect(importCadFile).toHaveBeenCalledWith('cad-1', file, expect.anything())
    })

    it('deletes the replaced CAD file record before creating the new one', async () => {
        fakeImports()
        vi.mocked(createCadFile).mockResolvedValue(written)
        const { imports } = setup()

        await imports.start({ machineId: 'm-1', file, replaceId: 'cad-old' })

        expect(deleteRecord).toHaveBeenCalledWith({ params: { id: 'cad-old' } })
        expect(vi.mocked(deleteRecord).mock.invocationCallOrder[0]).toBeLessThan(
            vi.mocked(createCadFile).mock.invocationCallOrder[0],
        )
    })

    it('replaces again after the old record was deleted but the new one not created', async () => {
        fakeImports()
        vi.mocked(deleteRecord).mockRejectedValue(new HttpError('NotFound', 404, 'Not found'))
        vi.mocked(createCadFile).mockResolvedValue(written)
        const { imports, items } = setup()

        await imports.start({ machineId: 'm-1', file, replaceId: 'cad-old' })

        expect(items()[0].cadFileId).toBe('cad-new')
    })

    it('refuses a second upload for the same machine, also while the first one starts', async () => {
        fakeImports()
        vi.mocked(createCadFile).mockResolvedValue(written)
        const { imports } = setup()

        const first = imports.start({ machineId: 'm-1', file })
        await expect(imports.start({ machineId: 'm-1', file })).rejects.toThrow()
        await first
        await expect(imports.start({ machineId: 'm-1', file })).rejects.toThrow()
        expect(createCadFile).toHaveBeenCalledOnce()
    })

    it('passes a failed registration to the caller and starts nothing', async () => {
        vi.mocked(createCadFile).mockRejectedValue(new Error('max_per_parent'))
        const { imports, items } = setup()

        await expect(imports.start({ machineId: 'm-1', file })).rejects.toThrow()
        expect(items()).toEqual([])
        expect(importCadFile).not.toHaveBeenCalled()
    })

    it('cancels only while the file uploads', async () => {
        const runs = fakeImports()
        vi.mocked(createCadFile).mockResolvedValue(written)
        const { imports } = setup()
        await imports.start({ machineId: 'm-1', file })
        const run = runs.get('cad-new')!

        run.uploaded()
        imports.cancel('m-1')
        expect(run.signal.aborted).toBe(false)

        vi.mocked(createCadFile).mockResolvedValue({ ...written, id: 'cad-2' })
        await imports.start({ machineId: 'm-2', file })
        imports.cancel('m-2')
        expect(runs.get('cad-2')!.signal.reason).toBe(CANCELLED)
    })

    it('stops following the files once unmounted', async () => {
        const runs = fakeImports()
        vi.mocked(createCadFile).mockResolvedValue(written)
        const { imports } = setup()
        await imports.start({ machineId: 'm-1', file })

        imports.setMounted(false)

        expect(runs.get('cad-new')!.signal.aborted).toBe(true)
        expect(runs.get('cad-new')!.signal.reason).not.toBe(CANCELLED)
    })
})
