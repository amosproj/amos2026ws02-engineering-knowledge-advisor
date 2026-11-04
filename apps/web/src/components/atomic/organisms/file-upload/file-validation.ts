export type FileUploadMode = 'single' | 'multiple'

export type FileRejectionCode =
    'invalid-type' | 'too-large' | 'empty-file' | 'too-many-files' | 'duplicate' | 'directory'

export type FileRejection = {
    code: FileRejectionCode
    message: string
}

export type FileCandidate = {
    file: File
    isDirectory: boolean
}

export type FileSelectionOptions = {
    mode: FileUploadMode
    current: readonly File[]
    accept?: readonly string[]
    maxSize?: number
    maxFiles?: number
}

export type FileSelectionResult = {
    files: File[]
    rejections: FileRejection[]
}

const SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB']

export function formatFileSize(bytes: number): string {
    const exponent = bytes > 0 ? Math.floor(Math.log(bytes) / Math.log(1024)) : 0
    const unitIndex = Math.min(exponent, SIZE_UNITS.length - 1)
    const value = bytes / 1024 ** unitIndex

    return `${Number.isInteger(value) ? value : value.toFixed(1)} ${SIZE_UNITS[unitIndex]}`
}

export function getFileKey(file: File): string {
    return `${file.name}:${file.size}:${file.lastModified}`
}

export function matchesAccept(file: File, accept: readonly string[] | undefined): boolean {
    if (!accept?.length) {
        return true
    }

    const fileName = file.name.toLowerCase()
    const fileType = file.type.toLowerCase()

    return accept.some((entry) => {
        const pattern = entry.trim().toLowerCase()

        if (pattern.startsWith('.')) {
            return fileName.endsWith(pattern)
        }

        if (pattern.endsWith('/*')) {
            return fileType.startsWith(pattern.slice(0, -1))
        }

        return fileType === pattern
    })
}

function getCandidateRejection(
    { file, isDirectory }: FileCandidate,
    { accept, maxSize }: FileSelectionOptions,
): FileRejection | null {
    if (isDirectory) {
        return { code: 'directory', message: `"${file.name}" is a folder. Select files only.` }
    }

    if (!matchesAccept(file, accept)) {
        return {
            code: 'invalid-type',
            message: `[${file.name}] has an unsupported file type. Accepted: ${accept?.join(', ')}.`,
        }
    }

    if (file.size === 0) {
        return { code: 'empty-file', message: `"${file.name}" is empty.` }
    }

    if (maxSize !== undefined && file.size > maxSize) {
        return {
            code: 'too-large',
            message: `[${file.name}] exceeds the ${formatFileSize(maxSize)} limit.`,
        }
    }

    return null
}

export function selectFiles(
    candidates: readonly FileCandidate[],
    options: FileSelectionOptions,
): FileSelectionResult {
    const { mode, current, maxFiles } = options

    if (mode === 'single') {
        if (candidates.length > 1) {
            return {
                files: [...current],
                rejections: [{ code: 'too-many-files', message: 'Select only one file.' }],
            }
        }

        const [candidate] = candidates
        const rejection = candidate ? getCandidateRejection(candidate, options) : null

        if (!candidate || rejection) {
            return { files: [...current], rejections: rejection ? [rejection] : [] }
        }

        return { files: [candidate.file], rejections: [] }
    }

    const files = [...current]
    const knownKeys = new Set(current.map(getFileKey))
    const rejections: FileRejection[] = []

    for (const candidate of candidates) {
        const rejection = getCandidateRejection(candidate, options)

        if (rejection) {
            rejections.push(rejection)
            continue
        }

        const { file } = candidate
        const key = getFileKey(file)

        if (knownKeys.has(key)) {
            rejections.push({
                code: 'duplicate',
                message: `[${file.name}] is already selected.`,
            })
            continue
        }

        if (maxFiles !== undefined && files.length >= maxFiles) {
            rejections.push({
                code: 'too-many-files',
                message: `[${file.name}] was not added: the limit is ${maxFiles} file${maxFiles === 1 ? '' : 's'}.`,
            })
            continue
        }

        knownKeys.add(key)
        files.push(file)
    }

    return { files, rejections }
}
