import * as React from 'react'

export type ImportPhase =
    'queued' | 'uploading' | 'processing' | 'ready' | 'failed' | 'cancelled' | 'processing_timeout'

export type ImportItem = {
    cadFileId: string
    assemblyGroupId: string
    name: string
    size: number
    phase: ImportPhase
    percent: number
    message?: string
}

type CadFileImportContextValue = {
    // Files of the imports started in this tab, until they are all done
    items: ImportItem[]
    // Resolves once the files are registered, the uploads then continue in the background.
    startImport: (assemblyGroupId: string, files: File[]) => Promise<void>
    // Only while the file is queued or uploading
    cancelImport: (cadFileId: string) => void
}

export const CadFileImportContext = React.createContext<CadFileImportContextValue | null>(null)

export function useCadFileImport() {
    const context = React.useContext(CadFileImportContext)
    if (!context) throw new Error('useCadFileImport must be used within CadFileImportProvider')
    return context
}

export function isCancellable(item: ImportItem) {
    return item.phase === 'queued' || item.phase === 'uploading'
}

/** Whether a file of these groups still uploads from this tab: deleting them now would let it land later. */
export function hasPendingUpload(items: ImportItem[], assemblyGroupIds: string[]) {
    return items.some(
        (item) => isCancellable(item) && assemblyGroupIds.includes(item.assemblyGroupId),
    )
}
