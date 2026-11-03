import { HttpError, NetworkError } from '@queries/query-errors'

import { cadFileErrorMessage, errorMessage } from '../models/machine-errors'
import {
    completeCadFile,
    deleteCadFile,
    getCadFile,
    type CadFile,
    type RegisteredCadFile,
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

/** Upload a registered CAD file, confirm it and wait for the end of its processing. */
export async function importCadFile(
    cadFile: RegisteredCadFile,
    file: File,
    { onProgress, onUploaded, signal }: ImportOptions,
): Promise<ImportResult> {
    const { id, upload } = cadFile
    try {
        await uploadFile(upload.url, upload.fields, file, { onProgress, signal })
    } catch (error) {
        if (!signal.aborted) return remove(id, failed(error))
    }
    // Also when the cancel lands as the upload succeeds
    if (signal.aborted) {
        return signal.reason === CANCELLED ? remove(id, { status: 'cancelled' }) : stopped
    }

    onUploaded()
    let state: CadFile
    try {
        state = await completeWithRetry(id, signal)
    } catch (error) {
        if (signal.aborted) return stopped
        // The file would otherwise stay uploading on the server until it expires
        if (errorCode(error) === 'upload_not_found') return remove(id, failed(error))
        return failed(error)
    }

    const deadline = new AbortController()
    const timer = setTimeout(() => deadline.abort(), MAX_PROCESSING_MS)
    try {
        const result = await waitForProcessing(
            id,
            state,
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
    state: CadFile,
    signal: AbortSignal,
): Promise<ImportResult | null> {
    while (state.status !== 'ready' && state.status !== 'failed') {
        await delay(2_000, signal)
        if (signal.aborted) return null
        try {
            state = await getCadFile({ params: { id }, signal })
        } catch (error) {
            if (signal.aborted) return null
            if (!isTransient(error)) return failed(error)
        }
    }

    return state.status === 'ready'
        ? { status: 'ready' }
        : { status: 'failed', message: cadFileErrorMessage(state.error_code) }
}

/** A completion is safe to repeat: it returns the current state once the file left uploading. */
async function completeWithRetry(id: string, signal: AbortSignal) {
    for (let attempt = 1; ; attempt++) {
        try {
            return await completeCadFile({ params: { id }, signal })
        } catch (error) {
            if (!(isTransient(error) || isBusy(error)) || attempt === 3) throw error
            await delay(attempt * 1_000, signal)
        }
    }
}

/** Delete the file on the server, then report `result`. */
async function remove(id: string, result: ImportResult): Promise<ImportResult> {
    try {
        await deleteCadFile({ params: { id } })
    } catch (error) {
        if (!(error instanceof HttpError && error._tag === 'NotFound')) {
            return {
                status: 'failed',
                message: `The upload was stopped, but the server could not remove the file: ${errorMessage(error)}`,
            }
        }
    }
    return result
}

const stopped: ImportResult = { status: 'stopped' }

function failed(error: unknown): ImportResult {
    const code = errorCode(error)
    return { status: 'failed', message: code ? cadFileErrorMessage(code) : errorMessage(error) }
}

function errorCode(error: unknown) {
    const code = error instanceof HttpError ? error.problem?.error_code : undefined
    return typeof code === 'string' ? code : undefined
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
