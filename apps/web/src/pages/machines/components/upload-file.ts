export class UploadError extends Error {
    constructor(status: number) {
        super(
            status === 0
                ? 'The upload was interrupted. Check your connection and import the file again.'
                : `The storage rejected the upload (HTTP ${status}).`,
        )
        this.name = 'UploadError'
    }
}

type UploadOptions = {
    onProgress: (percent: number) => void
    signal: AbortSignal
}

/** Post the file to a presigned form. XHR because fetch does not report upload progress. */
export function uploadFile(
    url: string,
    fields: Record<string, string>,
    file: File,
    { onProgress, signal }: UploadOptions,
): Promise<void> {
    return new Promise((resolve, reject) => {
        const body = new FormData()
        for (const [key, value] of Object.entries(fields)) body.append(key, value)
        body.append('file', file)

        const xhr = new XMLHttpRequest()
        let lastPercent = -1

        xhr.upload.onprogress = (event) => {
            // The browser may still report progress once the upload is aborted
            if (!event.lengthComputable || signal.aborted) return
            const percent = Math.floor((event.loaded / event.total) * 100)
            if (percent === lastPercent) return
            lastPercent = percent
            onProgress(percent)
        }
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) resolve()
            else reject(new UploadError(xhr.status))
        }
        xhr.onerror = () => reject(new UploadError(0))
        xhr.onabort = () => reject(new DOMException('Upload cancelled', 'AbortError'))

        if (signal.aborted) {
            reject(new DOMException('Upload cancelled', 'AbortError'))
            return
        }
        signal.addEventListener('abort', () => xhr.abort(), { once: true })

        xhr.open('POST', url)
        xhr.send(body)
    })
}
