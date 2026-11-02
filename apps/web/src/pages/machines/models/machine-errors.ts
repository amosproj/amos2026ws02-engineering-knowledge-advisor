const errorMessages: Record<string, string> = {
    upload_not_found: 'The file did not reach the server. Import it again.',
    file_mismatch: 'The uploaded file does not match the selected file. Import it again.',
    invalid_step_file: 'The file is not a valid STEP file.',
    duplicate_file: 'This STEP file has already been imported.',
}

export function machineErrorMessage(errorCode: string | null) {
    return (errorCode && errorMessages[errorCode]) || 'The import failed. Try again.'
}
