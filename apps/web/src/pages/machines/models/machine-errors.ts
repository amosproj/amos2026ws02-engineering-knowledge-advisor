import { HttpError } from '@queries/query-errors'

const errorMessages: Record<string, string> = {
    upload_not_found: 'The file did not reach the server. Upload it again.',
    file_mismatch: 'The uploaded file does not match the selected file. Upload it again.',
    invalid_step_file: 'The file is not a valid STEP file.',
    upload_exists: 'The file is already processed or ready.',
    max_per_parent: 'This machine already has a CAD file.',
}

export function cadFileErrorMessage(errorCode: string | null | undefined) {
    return (errorCode && errorMessages[errorCode]) || 'The upload failed. Try again.'
}

export function errorCode(error: unknown) {
    const code = error instanceof HttpError ? error.problem?.errorCode : undefined
    return typeof code === 'string' ? code : undefined
}

export function isStale(error: unknown) {
    return error instanceof HttpError && error.status === 412
}

/** The problem detail sent by the API, or the error message. */
export function errorMessage(error: unknown) {
    const code = errorCode(error)
    if (code && errorMessages[code]) return errorMessages[code]
    if (error instanceof HttpError && error.problem?.detail) return error.problem.detail
    return error instanceof Error ? error.message : 'Something went wrong. Try again.'
}
