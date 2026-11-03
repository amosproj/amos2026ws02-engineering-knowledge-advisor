import { HttpError } from '@queries/query-errors'

const errorMessages: Record<string, string> = {
    upload_not_found: 'The file did not reach the server. Import it again.',
    file_mismatch: 'The uploaded file does not match the selected file. Import it again.',
    invalid_step_file: 'The file is not a valid STEP file.',
    duplicate_file: 'This STEP file has already been imported.',
}

export function cadFileErrorMessage(errorCode: string | null) {
    return (errorCode && errorMessages[errorCode]) || 'The import failed. Try again.'
}

/** The problem detail sent by the API, or the error message. */
export function errorMessage(error: unknown) {
    if (error instanceof HttpError && error.problem?.detail) return error.problem.detail
    return error instanceof Error ? error.message : 'Something went wrong. Try again.'
}
