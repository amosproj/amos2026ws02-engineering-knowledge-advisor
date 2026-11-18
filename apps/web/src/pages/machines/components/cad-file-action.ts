import type { findCadFile } from '../models/machine-model'
import type { MachineView } from '../query/machine-api'

export type CadFileAction =
    { kind: 'upload' } | { kind: 'retry'; cadFileId: string; interrupted: boolean }

export const cadFileActionLabels: Record<CadFileAction['kind'], string> = {
    upload: 'Upload CAD file',
    retry: 'Upload CAD file again',
}

export function toCadFileAction(
    status: MachineView['status'],
    cadFile: ReturnType<typeof findCadFile>,
): CadFileAction | null {
    if (!cadFile) return { kind: 'upload' }
    // Replacing a ready file is not possible yet, the backend refuses a second assembly tree
    if (status === 'ready' || status === 'processing') return null
    return { kind: 'retry', cadFileId: cadFile['@id'], interrupted: status === 'uploading' }
}
