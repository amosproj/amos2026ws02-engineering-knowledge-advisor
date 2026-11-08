import { HttpError, NetworkError } from '@queries/query-errors'

import { cadFileErrorMessage, errorCode, errorMessage } from '../models/machine-errors'
import {
    completeUpload,
    deleteRecord,
    getCadFile,
    requestUploadForm,
    type CadFileView,
} from '../query/machine-api'
import { uploadFile } from './upload-file'

// After this, the processing is left to the server so the import does not stay open forever
export const MAX_PROCESSING_MS = 15 * 60_000

/** Abort reason of a cancel by the user. Any other reason only stops following the file. */
export const CANCELLED = 'cancelled'

export type ImportResult =
    | { status: 'ready' }
    | { status: 'failed'; message: string }
    | { status: 'cancelled' }
    | { status: 'processing_timeout' }
    | { status: 'stopped' }

type ImportOptions = {
    onProgress: (percent: number) => void
    onUploaded: () => void // Called once the upload is over, cancelling is no longer possible after it.
    signal: AbortSignal
}

export async function importCadFile(
    cadFileId: string,
    file: File,
    { onProgress, onUploaded, signal }: ImportOptions,
): Promise<ImportResult> {
    try {
        const form = await requestUploadForm({
            params: { id: cadFileId },
            body: { size: file.size },
            signal,
        })
        await uploadFile(form.url, form.fields, file, { onProgress, signal })
    } catch (error) {
        if (!signal.aborted) return failed(error)
    }
    // Also when the cancel lands as the upload succeeds
    if (signal.aborted) {
        return signal.reason === CANCELLED ? remove(cadFileId) : stopped
    }

    onUploaded()
    let status: string
    try {
        status = (await completeWithRetry(cadFileId, signal)).status
    } catch (error) {
        return signal.aborted ? stopped : failed(error)
    }

    const deadline = new AbortController()
    const timer = setTimeout(() => deadline.abort(), MAX_PROCESSING_MS)
    try {
        const result = await waitForProcessing(
            cadFileId,
            status,
            AbortSignal.any([signal, deadline.signal]),
        )
        return result ?? (signal.aborted ? stopped : { status: 'processing_timeout' })
    } finally {
        clearTimeout(timer)
    }
}

/** Poll until the file is ready or failed, null once `signal` aborts. */
async function waitForProcessing(
    id: string,
    status: string,
    signal: AbortSignal,
): Promise<ImportResult | null> {
    let view: CadFileView | undefined
    while (status !== 'ready' && status !== 'failed') {
        await delay(2_000, signal)
        if (signal.aborted) return null
        try {
            view = await getCadFile({
                params: { id },
                search: { include: 'status,upload' },
                signal,
            })
        } catch (error) {
            if (signal.aborted) return null
            if (!isTransient(error)) return failed(error)
            continue
        }
        if (!view.upload) return { status: 'failed', message: 'The CAD file was removed.' }
        status = view.upload.status
    }

    return status === 'ready'
        ? { status: 'ready' }
        : { status: 'failed', message: cadFileErrorMessage(view?.upload?.errorCode) }
}

/** A completion is safe to repeat: it returns the current state once the file left uploading. */
async function completeWithRetry(id: string, signal: AbortSignal) {
    for (let attempt = 1; ; attempt++) {
        try {
            return await completeUpload({ params: { id }, signal })
        } catch (error) {
            if (!(isTransient(error) || isBusy(error)) || attempt === 3) throw error
            await delay(attempt * 1_000, signal)
        }
    }
}

async function remove(id: string): Promise<ImportResult> {
    try {
        await deleteRecord({ params: { id } })
    } catch (error) {
        if (!(error instanceof HttpError && error._tag === 'NotFound')) {
            return {
                status: 'failed',
                message: `The upload was stopped, but the server could not remove the file: ${errorMessage(error)}`,
            }
        }
    }
    return { status: 'cancelled' }
}

const stopped: ImportResult = { status: 'stopped' }

function failed(error: unknown): ImportResult {
    return { status: 'failed', message: errorMessage(error) }
}

function isTransient(error: unknown) {
    return (
        error instanceof NetworkError ||
        (error instanceof HttpError && error._tag === 'ServerError')
    )
}

/** The worker holds the file for a moment: a conflict without error code. */
function isBusy(error: unknown) {
    return error instanceof HttpError && error._tag === 'Conflict' && !errorCode(error)
}

/** Wait for `ms`, or less if the signal aborts. */
function delay(ms: number, signal: AbortSignal) {
    return new Promise<void>((resolve) => {
        const done = () => {
            clearTimeout(timer)
            signal.removeEventListener('abort', done)
            resolve()
        }
        const timer = setTimeout(done, ms)
        signal.addEventListener('abort', done)
    })
}
