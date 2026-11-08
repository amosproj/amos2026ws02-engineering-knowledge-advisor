import * as React from 'react'

export type ImportPhase = 'uploading' | 'processing'

export type ImportItem = {
    machineId: string
    cadFileId: string
    name: string
    size: number
    phase: ImportPhase
    percent: number
}

export type ImportTarget = {
    machineId: string
    file: File
    reuseId?: string
    replaceId?: string
}

type CadFileImportContextValue = {
    items: ImportItem[]
    // Resolves once the CAD file record is ready, the upload then continues in the background.
    startImport: (target: ImportTarget) => Promise<void>
    cancelImport: (machineId: string) => void
}

export const CadFileImportContext = React.createContext<CadFileImportContextValue | null>(null)

export function useCadFileImport() {
    const context = React.useContext(CadFileImportContext)
    if (!context) throw new Error('useCadFileImport must be used within CadFileImportProvider')
    return context
}
