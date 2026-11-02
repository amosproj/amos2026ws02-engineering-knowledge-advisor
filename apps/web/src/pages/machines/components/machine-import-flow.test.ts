import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { HttpError, NetworkError } from '@queries/query-errors'
import {
    completeMachineUpload,
    deleteMachine,
    getMachine,
    type MachineState,
} from '../query/machine-api'
import { followMachineImport } from './machine-import-flow'

vi.mock('../query/machine-api', () => ({
    completeMachineUpload: vi.fn(),
    deleteMachine: vi.fn(),
    getMachine: vi.fn(),
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

const machine = { id: 'm1', upload: { url: '/storage/bucket', fields: { key: 'machines/m1' } } }
const file = new File(['ISO-10303-21;'], 'press.step')
const state = (status: MachineState['status'], error_code: string | null = null) => ({
    id: 'm1',
    status,
    error_code,
})
const conflict = (errorCode: string) =>
    new HttpError('Conflict', 409, 'The machine import failed', {
        type: 'about:blank',
        error_code: errorCode,
    })

function start() {
    const controller = new AbortController()
    const onProgress = vi.fn()
    const onProcessing = vi.fn()
    const result = followMachineImport(machine, file, {
        onProgress,
        onProcessing,
        signal: controller.signal,
    })
    return { controller, onProgress, onProcessing, result, xhr: FakeXhr.last }
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

describe('followMachineImport', () => {
    it('uploads, completes and polls until the machine is ready', async () => {
        vi.mocked(completeMachineUpload).mockResolvedValue(state('processing'))
        vi.mocked(getMachine)
            .mockResolvedValueOnce(state('processing'))
            .mockResolvedValueOnce(state('ready'))
        const { result, xhr, onProgress, onProcessing } = start()

        xhr.progress(1, 300)
        xhr.progress(2, 300)
        xhr.progress(300, 300)
        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({ status: 'ready' })
        expect([...xhr.body!.keys()]).toEqual(['key', 'file'])
        expect(onProgress.mock.calls).toEqual([[0], [100]])
        expect(onProcessing).toHaveBeenCalledOnce()
        expect(getMachine).toHaveBeenCalledTimes(2)
    })

    it('fails without completing when the storage rejects the upload', async () => {
        const { result, xhr } = start()

        xhr.respond(403)

        await expect(settle(result)).resolves.toMatchObject({ status: 'failed' })
        expect(completeMachineUpload).not.toHaveBeenCalled()
    })

    it('deletes the machine when cancelled during the upload', async () => {
        const { result, controller } = start()

        controller.abort()

        await expect(settle(result)).resolves.toEqual({ status: 'cancelled' })
        expect(deleteMachine).toHaveBeenCalledWith({ params: { id: 'm1' } })
        expect(completeMachineUpload).not.toHaveBeenCalled()
    })

    it('still cancels when the cancel lands as the upload succeeds', async () => {
        const { result, xhr, controller, onProcessing } = start()

        xhr.respond(204)
        controller.abort()

        await expect(settle(result)).resolves.toEqual({ status: 'cancelled' })
        expect(onProcessing).not.toHaveBeenCalled()
        expect(completeMachineUpload).not.toHaveBeenCalled()
    })

    it('retries the completion after a transient failure', async () => {
        vi.mocked(completeMachineUpload)
            .mockRejectedValueOnce(new NetworkError(new TypeError('Failed to fetch')))
            .mockResolvedValueOnce(state('ready'))
        const { result, xhr } = start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({ status: 'ready' })
        expect(completeMachineUpload).toHaveBeenCalledTimes(2)
    })

    it('reports the error code when the completion is rejected', async () => {
        vi.mocked(completeMachineUpload).mockRejectedValue(conflict('file_mismatch'))
        const { result, xhr } = start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({
            status: 'failed',
            message: 'The uploaded file does not match the selected file. Import it again.',
        })
        expect(completeMachineUpload).toHaveBeenCalledOnce()
    })

    it('keeps polling through transient errors until the machine fails', async () => {
        vi.mocked(completeMachineUpload).mockResolvedValue(state('processing'))
        vi.mocked(getMachine)
            .mockRejectedValueOnce(new NetworkError(new TypeError('Failed to fetch')))
            .mockResolvedValueOnce(state('failed', 'invalid_step_file'))
        const { result, xhr } = start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({
            status: 'failed',
            message: 'The file is not a valid STEP file.',
        })
    })

    it('stops polling when the machine no longer exists', async () => {
        vi.mocked(completeMachineUpload).mockResolvedValue(state('processing'))
        vi.mocked(getMachine).mockRejectedValue(new HttpError('NotFound', 404, 'Machine not found'))
        const { result, xhr } = start()

        xhr.respond(204)

        await expect(settle(result)).resolves.toEqual({
            status: 'failed',
            message: 'Machine not found',
        })
        expect(getMachine).toHaveBeenCalledOnce()
    })
})
