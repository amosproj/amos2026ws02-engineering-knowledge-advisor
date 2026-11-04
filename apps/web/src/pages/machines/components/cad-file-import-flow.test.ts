import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { HttpError, NetworkError } from '@queries/query-errors'
import {
    completeCadFile,
    deleteCadFile,
    getCadFile,
    type CadFile,
    type CadFileStatus,
} from '../query/machine-api'
import { CANCELLED, importCadFile, MAX_PROCESSING_MS } from './cad-file-import-flow'

vi.mock('../query/machine-api', () => ({
    completeCadFile: vi.fn(),
    deleteCadFile: vi.fn(),
    getCadFile: vi.fn(),
}))

class FakeXhr {
    static last: FakeXhr
    upload: { onprogress?: (event: Partial<ProgressEvent>) => void } = {}
    status = 0
    body?: FormData
    onload?: () => void
    onerror?: () => void
    onabort?: () => void

    constructor() {
        FakeXhr.last = this
    }
    open() {}
    send(body: FormData) {
        this.body = body
    }
    abort() {
        this.onabort?.()
    }
    progress(loaded: number, total: number) {
        this.upload.onprogress?.({ lengthComputable: true, loaded, total })
    }
    respond(status: number) {
        this.status = status
        this.onload?.()
    }
}

const cadFile = {
    id: 'cad-1',
    name: 'press.step',
    upload: { url: '/storage/bucket', fields: { key: 'machines/m/cad-1/source.step' } },
}
const file = new File(['ISO-10303-21;'], 'press.step')
const state = (status: CadFileStatus, error_code: string | null = null): CadFile => ({
    id: 'cad-1',
    name: 'press.step',
    assembly_group_id: 'ag-1',
    status,
    error_code,
    size_bytes: file.size,
    created_at: '2026-11-03T10:00:00Z',
    updated_at: '2026-11-03T10:00:00Z',
})
const conflict = (errorCode?: string) =>
    new HttpError('Conflict', 409, 'Conflict', {
        type: 'about:blank',
        ...(errorCode ? { error_code: errorCode } : {}),
    })
const notFound = () => new HttpError('NotFound', 404, 'Not found')
const deleted = { params: { id: 'cad-1' } }

function start() {
    const controller = new AbortController()
    const onProgress = vi.fn()
    const onUploaded = vi.fn()
    const result = importCadFile(cadFile, file, {
        onProgress,
        onUploaded,
        signal: controller.signal,
    })
    return { controller, onProgress, onUploaded, result, xhr: FakeXhr.last }
}

async function settle<T>(promise: Promise<T>) {
    await vi.runAllTimersAsync()
    return promise
}

beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
})

afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.resetAllMocks()
})

describe('importCadFile', () => {
    it('uploads, completes and polls until the file is ready', async () => {
        vi.mocked(completeCadFile).mockResolvedValue(state('processing'))
        vi.mocked(getCadFile)
            .mockResolvedValueOnce(state('processing'))
            .mockResolvedValueOnce(state('ready'))
        const { result, xhr, onProgress, onUploaded } = start()

        xhr.progress(1, 300)
        xhr.progress(300, 300)
        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({ status: 'ready' })
        expect([...xhr.body!.keys()]).toEqual(['key', 'file'])
        expect(onProgress.mock.calls).toEqual([[0], [100]])
        expect(onUploaded).toHaveBeenCalledOnce()
        expect(getCadFile).toHaveBeenCalledTimes(2)
        expect(deleteCadFile).not.toHaveBeenCalled()
    })

    it('deletes the file when the storage rejects the upload, as for an expired form', async () => {
        const { result, xhr } = start()

        xhr.respond(403)

        await expect(settle(result)).resolves.toMatchObject({ status: 'failed' })
        expect(deleteCadFile).toHaveBeenCalledWith(deleted)
        expect(completeCadFile).not.toHaveBeenCalled()
    })

    it('deletes the file when cancelled during the upload', async () => {
        const { result, controller } = start()

        controller.abort(CANCELLED)

        await expect(settle(result)).resolves.toEqual({ status: 'cancelled' })
        expect(deleteCadFile).toHaveBeenCalledWith(deleted)
        expect(completeCadFile).not.toHaveBeenCalled()
    })

    it('still cancels when the cancel lands as the upload succeeds', async () => {
        const { result, xhr, controller, onUploaded } = start()

        xhr.respond(204)
        controller.abort(CANCELLED)

        await expect(settle(result)).resolves.toEqual({ status: 'cancelled' })
        expect(onUploaded).not.toHaveBeenCalled()
        expect(completeCadFile).not.toHaveBeenCalled()
    })

    it('stops without deleting when the page goes away', async () => {
        const { result, controller } = start()

        controller.abort()

        await expect(settle(result)).resolves.toEqual({ status: 'stopped' })
        expect(deleteCadFile).not.toHaveBeenCalled()
    })

    it('treats a file already deleted on the server as removed', async () => {
        vi.mocked(deleteCadFile).mockRejectedValue(notFound())
        const { result, controller } = start()

        controller.abort(CANCELLED)

        await expect(settle(result)).resolves.toEqual({ status: 'cancelled' })
    })

    it('reports a cleanup the server refused', async () => {
        vi.mocked(deleteCadFile).mockRejectedValue(conflict())
        const { result, controller } = start()

        controller.abort(CANCELLED)

        await expect(settle(result)).resolves.toMatchObject({ status: 'failed' })
    })

    it('retries the completion after a network error or while the file is busy', async () => {
        vi.mocked(completeCadFile)
            .mockRejectedValueOnce(new NetworkError(new TypeError('Failed to fetch')))
            .mockRejectedValueOnce(conflict())
            .mockResolvedValueOnce(state('ready'))
        const { result, xhr } = start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({ status: 'ready' })
        expect(completeCadFile).toHaveBeenCalledTimes(3)
    })

    it('reports the error code of a refused completion and keeps the failed file', async () => {
        vi.mocked(completeCadFile).mockRejectedValue(conflict('file_mismatch'))
        const { result, xhr } = start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({
            status: 'failed',
            message: 'The uploaded file does not match the selected file. Import it again.',
        })
        expect(completeCadFile).toHaveBeenCalledOnce()
        expect(deleteCadFile).not.toHaveBeenCalled()
    })

    it('deletes the file when the server did not receive the upload', async () => {
        vi.mocked(completeCadFile).mockRejectedValue(conflict('upload_not_found'))
        const { result, xhr } = start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toMatchObject({ status: 'failed' })
        expect(deleteCadFile).toHaveBeenCalledWith(deleted)
    })

    it('keeps polling through transient errors until the file fails', async () => {
        vi.mocked(completeCadFile).mockResolvedValue(state('processing'))
        vi.mocked(getCadFile)
            .mockRejectedValueOnce(new NetworkError(new TypeError('Failed to fetch')))
            .mockResolvedValueOnce(state('failed', 'duplicate_file'))
        const { result, xhr } = start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({
            status: 'failed',
            message: 'This STEP file has already been imported.',
        })
    })

    it('gives up waiting once the processing takes too long', async () => {
        vi.mocked(completeCadFile).mockResolvedValue(state('processing'))
        vi.mocked(getCadFile).mockResolvedValue(state('processing'))
        const { result, xhr } = start()

        xhr.respond(204)
        await vi.advanceTimersByTimeAsync(MAX_PROCESSING_MS)

        await expect(result).resolves.toEqual({ status: 'processing_timeout' })
        const polls = vi.mocked(getCadFile).mock.calls.length
        await vi.advanceTimersByTimeAsync(10_000)
        expect(getCadFile).toHaveBeenCalledTimes(polls)
    })

    it('stops polling when the page goes away', async () => {
        vi.mocked(completeCadFile).mockResolvedValue(state('processing'))
        vi.mocked(getCadFile).mockResolvedValue(state('processing'))
        const { result, xhr, controller } = start()

        xhr.respond(204)
        await vi.advanceTimersByTimeAsync(5_000)
        controller.abort()

        await expect(settle(result)).resolves.toEqual({ status: 'stopped' })
    })
})
