import * as React from 'react'

import type { MachineImport } from '../models/import-machine-model'

export type ImportPhase = 'uploading' | 'processing'

export type ActiveImport = {
    machineId: string
    name: string
    description?: string
    file: File
    phase: ImportPhase
    percent: number
}

type MachineImportContextValue = {
    activeImport: ActiveImport | null
    // Resolves once the machine is created, the upload then continues in the background.
    startImport: (machineImport: MachineImport) => Promise<void>
    cancelImport: () => void
}

export const MachineImportContext = React.createContext<MachineImportContextValue | null>(null)

export function useMachineImport() {
    const context = React.useContext(MachineImportContext)
    if (!context) throw new Error('useMachineImport must be used within MachineImportProvider')
    return context
}
