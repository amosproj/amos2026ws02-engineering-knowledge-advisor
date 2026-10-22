function getErrorMessage(error: unknown): string | undefined {
    if (typeof error === 'string') {
        return error
    }

    if (
        typeof error === 'object' &&
        error !== null &&
        'message' in error &&
        typeof error.message === 'string'
    ) {
        return error.message
    }

    return undefined
}

export function getVisibleFieldErrors(
    errors: readonly unknown[],
    isTouched: boolean,
): Array<{ message: string }> {
    if (!isTouched) {
        return []
    }

    return errors
        .map(getErrorMessage)
        .filter((message): message is string => message !== undefined)
        .map((message) => ({ message }))
}
