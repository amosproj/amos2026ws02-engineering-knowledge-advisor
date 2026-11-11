import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { HttpError, NetworkError } from '@queries/query-errors'
import {
    completeUpload,
    deleteRecord,
    getCadFile,
    requestUploadForm,
    type CadFileView,
    type FileStatus,
} from '../query/machine-api'
import { CANCELLED, importCadFile, MAX_PROCESSING_MS } from './cad-file-import-flow'

vi.mock('../query/machine-api', () => ({
    completeUpload: vi.fn(),
    deleteRecord: vi.fn(),
    getCadFile: vi.fn(),
    requestUploadForm: vi.fn(),
}))

class FakeXhr {
    static last: FakeXhr | undefined
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

const file = new File(['ISO-10303-21;'], 'press.step')
const form = { url: '/storage/bucket', fields: { key: 'files/cad-1/source.step' } }
const upload = (status: Exclude<FileStatus, 'empty'>, errorCode: string | null = null) => ({
    id: 'cad-1',
    status,
    errorCode,
    sizeBytes: file.size,
    createdAt: '2026-11-08T10:00:00Z',
    updatedAt: '2026-11-08T10:00:00Z',
})
const view = (
    status: Exclude<FileStatus, 'empty'>,
    errorCode: string | null = null,
): CadFileView => ({
    record: { '@id': 'cad-1', name: 'press.step' },
    version: '1',
    status,
    upload: upload(status, errorCode),
})
const conflict = (errorCode?: string) =>
    new HttpError('Conflict', 409, 'Conflict', {
        type: 'about:blank',
        ...(errorCode ? { errorCode } : {}),
    })
const notFound = () => new HttpError('NotFound', 404, 'Not found')
const deleted = { params: { id: 'cad-1' } }

async function start() {
    vi.mocked(requestUploadForm).mockResolvedValue(form)
    const controller = new AbortController()
    const onProgress = vi.fn()
    const onUploaded = vi.fn()
    const result = importCadFile('cad-1', file, {
        onProgress,
        onUploaded,
        signal: controller.signal,
    })
    await vi.advanceTimersByTimeAsync(0)
    return { controller, onProgress, onUploaded, result, xhr: FakeXhr.last! }
}

async function settle<T>(promise: Promise<T>) {
    await vi.runAllTimersAsync()
    return promise
}

beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    FakeXhr.last = undefined
})

afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.resetAllMocks()
})

describe('importCadFile', () => {
    it('asks for a form, uploads, completes and polls until the file is ready', async () => {
        vi.mocked(completeUpload).mockResolvedValue(upload('processing'))
        vi.mocked(getCadFile)
            .mockResolvedValueOnce(view('processing'))
            .mockResolvedValueOnce(view('ready'))
        const { result, xhr, onProgress, onUploaded } = await start()

        xhr.progress(1, 300)
        xhr.progress(300, 300)
        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({ status: 'ready' })
        expect(requestUploadForm).toHaveBeenCalledWith(
            expect.objectContaining({ params: { id: 'cad-1' }, body: { size: file.size } }),
        )
        expect([...xhr.body!.keys()]).toEqual(['key', 'file'])
        expect(onProgress.mock.calls).toEqual([[0], [100]])
        expect(onUploaded).toHaveBeenCalledOnce()
        expect(getCadFile).toHaveBeenCalledTimes(2)
        expect(getCadFile).toHaveBeenCalledWith(
            expect.objectContaining({ search: { include: 'status,upload' } }),
        )
        expect(deleteRecord).not.toHaveBeenCalled()
    })

    it('keeps the file when the form is refused, so it can be uploaded again', async () => {
        vi.mocked(requestUploadForm).mockRejectedValue(conflict('upload_exists'))
        const result = importCadFile('cad-1', file, {
            onProgress: vi.fn(),
            onUploaded: vi.fn(),
            signal: new AbortController().signal,
        })

        await expect(settle(result)).resolves.toEqual({
            status: 'failed',
            message: 'The file is already processed or ready.',
        })
        expect(FakeXhr.last).toBeUndefined()
        expect(deleteRecord).not.toHaveBeenCalled()
    })

    it('keeps the file when the storage rejects the upload', async () => {
        const { result, xhr } = await start()

        xhr.respond(403)

        await expect(settle(result)).resolves.toMatchObject({ status: 'failed' })
        expect(deleteRecord).not.toHaveBeenCalled()
        expect(completeUpload).not.toHaveBeenCalled()
    })

    it('deletes the file when cancelled during the upload', async () => {
        const { result, controller } = await start()

        controller.abort(CANCELLED)

        await expect(settle(result)).resolves.toEqual({ status: 'cancelled' })
        expect(deleteRecord).toHaveBeenCalledWith(deleted)
        expect(completeUpload).not.toHaveBeenCalled()
    })

    it('still cancels when the cancel lands as the upload succeeds', async () => {
        const { result, xhr, controller, onUploaded } = await start()

        xhr.respond(204)
        controller.abort(CANCELLED)

        await expect(settle(result)).resolves.toEqual({ status: 'cancelled' })
        expect(onUploaded).not.toHaveBeenCalled()
        expect(completeUpload).not.toHaveBeenCalled()
    })

    it('stops without deleting when the page goes away', async () => {
        const { result, controller } = await start()

        controller.abort()

        await expect(settle(result)).resolves.toEqual({ status: 'stopped' })
        expect(deleteRecord).not.toHaveBeenCalled()
    })

    it('treats a file already deleted on the server as removed', async () => {
        vi.mocked(deleteRecord).mockRejectedValue(notFound())
        const { result, controller } = await start()

        controller.abort(CANCELLED)

        await expect(settle(result)).resolves.toEqual({ status: 'cancelled' })
    })

    it('reports a cleanup the server refused', async () => {
        vi.mocked(deleteRecord).mockRejectedValue(conflict())
        const { result, controller } = await start()

        controller.abort(CANCELLED)

        await expect(settle(result)).resolves.toMatchObject({ status: 'failed' })
    })

    it('retries the completion after a network error or while the file is busy', async () => {
        vi.mocked(completeUpload)
            .mockRejectedValueOnce(new NetworkError(new TypeError('Failed to fetch')))
            .mockRejectedValueOnce(conflict())
            .mockResolvedValueOnce(upload('ready'))
        const { result, xhr } = await start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({ status: 'ready' })
        expect(completeUpload).toHaveBeenCalledTimes(3)
    })

    it('reports the error code of a refused completion and keeps the file', async () => {
        vi.mocked(completeUpload).mockRejectedValue(conflict('file_mismatch'))
        const { result, xhr } = await start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({
            status: 'failed',
            message: 'The uploaded file does not match the selected file. Upload it again.',
        })
        expect(completeUpload).toHaveBeenCalledOnce()
        expect(deleteRecord).not.toHaveBeenCalled()
    })

    it('keeps polling through transient errors until the file fails', async () => {
        vi.mocked(completeUpload).mockResolvedValue(upload('processing'))
        vi.mocked(getCadFile)
            .mockRejectedValueOnce(new NetworkError(new TypeError('Failed to fetch')))
            .mockResolvedValueOnce(view('failed', 'invalid_step_file'))
        const { result, xhr } = await start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({
            status: 'failed',
            message: 'The file is not a valid STEP file.',
        })
    })

    it('fails when the file is removed while it is processed', async () => {
        vi.mocked(completeUpload).mockResolvedValue(upload('processing'))
        vi.mocked(getCadFile).mockResolvedValue({ ...view('processing'), upload: null })
        const { result, xhr } = await start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toMatchObject({ status: 'failed' })
    })

    it('gives up waiting once the processing takes too long', async () => {
        vi.mocked(completeUpload).mockResolvedValue(upload('processing'))
        vi.mocked(getCadFile).mockResolvedValue(view('processing'))
        const { result, xhr } = await start()

        xhr.respond(204)
        await vi.advanceTimersByTimeAsync(MAX_PROCESSING_MS)

        await expect(result).resolves.toEqual({ status: 'processing_timeout' })
        const polls = vi.mocked(getCadFile).mock.calls.length
        await vi.advanceTimersByTimeAsync(10_000)
        expect(getCadFile).toHaveBeenCalledTimes(polls)
    })

    it('stops polling when the page goes away', async () => {
        vi.mocked(completeUpload).mockResolvedValue(upload('processing'))
        vi.mocked(getCadFile).mockResolvedValue(view('processing'))
        const { result, xhr, controller } = await start()

        xhr.respond(204)
        await vi.advanceTimersByTimeAsync(5_000)
        controller.abort()

        await expect(settle(result)).resolves.toEqual({ status: 'stopped' })
    })
})
