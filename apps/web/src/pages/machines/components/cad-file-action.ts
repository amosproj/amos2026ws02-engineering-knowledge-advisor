import type { findCadFile } from '../models/machine-model'
import type { MachineView } from '../query/machine-api'

export type CadFileAction =
    | { kind: 'upload' }
    | { kind: 'retry'; cadFileId: string; interrupted: boolean }
    | { kind: 'replace'; cadFileId: string; name: string }

export const cadFileActionLabels: Record<CadFileAction['kind'], string> = {
    upload: 'Upload CAD file',
    retry: 'Upload CAD file again',
    replace: 'Replace CAD file',
}

export function toCadFileAction(
    status: MachineView['status'],
    cadFile: ReturnType<typeof findCadFile>,
): CadFileAction | null {
    if (!cadFile) return { kind: 'upload' }
    if (status === 'ready') {
        return { kind: 'replace', cadFileId: cadFile['@id'], name: cadFile.name ?? 'The file' }
    }
    if (status === 'processing') return null
    return { kind: 'retry', cadFileId: cadFile['@id'], interrupted: status === 'uploading' }
}
