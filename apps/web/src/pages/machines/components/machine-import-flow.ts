import { HttpError, NetworkError } from '@queries/query-errors'

import {
    completeMachineUpload,
    deleteMachine,
    getMachine,
    type MachineState,
} from '../query/machine-api'
import { uploadFile } from './upload-file'

const errorMessages: Record<string, string> = {
    upload_not_found: 'The file did not reach the server. Import it again.',
    file_mismatch: 'The uploaded file does not match the selected file. Import it again.',
    invalid_step_file: 'The file is not a valid STEP file.',
    duplicate_file: 'This STEP file has already been imported.',
}

export type ImportResult =
    { status: 'ready' } | { status: 'failed'; message: string } | { status: 'cancelled' }

type CreatedMachine = {
    id: string
    upload: { url: string; fields: Record<string, string> }
}

type FollowOptions = {
    onProgress: (percent: number) => void
    onProcessing: () => void // Called once the upload is over, cancelling is no longer possible after it.
    signal: AbortSignal
}

/** Upload the STEP file of a created machine, confirm it and wait for the end of its processing. */
export async function followMachineImport(
    machine: CreatedMachine,
    file: File,
    { onProgress, onProcessing, signal }: FollowOptions,
): Promise<ImportResult> {
    try {
        await uploadFile(machine.upload.url, machine.upload.fields, file, { onProgress, signal })
    } catch (error) {
        if (!signal.aborted) return failed(error)
    }
    if (signal.aborted) return cancel(machine.id)

    onProcessing()
    let state: MachineState
    try {
        state = await completeWithRetry(machine.id)
    } catch (error) {
        return failed(error)
    }

    while (state.status !== 'ready' && state.status !== 'failed') {
        await delay(2_000)
        try {
            state = await getMachine({ params: { id: machine.id } })
        } catch (error) {
            if (!isTransient(error)) return failed(error)
        }
    }

    return state.status === 'ready'
        ? { status: 'ready' }
        : { status: 'failed', message: errorMessage(state.error_code) }
}

async function completeWithRetry(id: string) {
    for (let attempt = 1; ; attempt++) {
        try {
            return await completeMachineUpload({ params: { id } })
        } catch (error) {
            if (!isTransient(error) || attempt === 3) throw error
            await delay(attempt * 1_000)
        }
    }
}

async function cancel(id: string): Promise<ImportResult> {
    try {
        await deleteMachine({ params: { id } })
        return { status: 'cancelled' }
    } catch {
        return {
            status: 'failed',
            message: 'The upload was stopped, but the server could not remove the import.',
        }
    }
}

function failed(error: unknown): ImportResult {
    const errorCode = error instanceof HttpError ? error.problem?.error_code : undefined
    if (typeof errorCode === 'string') return { status: 'failed', message: errorMessage(errorCode) }
    return {
        status: 'failed',
        message: error instanceof Error ? error.message : errorMessage(null),
    }
}

function errorMessage(errorCode: string | null) {
    return (errorCode && errorMessages[errorCode]) || 'The import failed. Try again.'
}

function isTransient(error: unknown) {
    return (
        error instanceof NetworkError ||
        (error instanceof HttpError && error._tag === 'ServerError')
    )
}

function delay(ms: number) {
    return new Promise((resolve) => setTimeout(resolve, ms))
}
