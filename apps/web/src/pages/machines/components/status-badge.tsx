import { cn } from 'cn'

import { Badge } from '@components'

import type { FileStatus } from '../query/machine-api'
import type { ImportItem } from './cad-file-import-context'

const statusStyles: Record<FileStatus, string> = {
    empty: 'bg-muted text-muted-foreground',
    uploading: 'bg-secondary text-secondary-foreground',
    processing: 'hazard-stripes animate-hazard text-hazard-foreground motion-reduce:animate-none',
    ready: 'bg-success/15 text-success',
    failed: 'bg-destructive/10 text-destructive dark:bg-destructive/20',
}

const statusLabels: Record<FileStatus, string> = {
    empty: 'No file',
    // Uploading on the server but not from this tab
    uploading: 'Interrupted',
    processing: 'Processing',
    ready: 'Ready',
    failed: 'Failed',
}

type StatusBadgeProps = {
    status: FileStatus
    importItem?: ImportItem
}

export function StatusBadge({ status, importItem }: StatusBadgeProps) {
    if (importItem?.phase === 'uploading') {
        return (
            <Badge className={cn('tabular-nums', statusStyles.uploading)}>
                Uploading {importItem.percent} %
            </Badge>
        )
    }
    const shown: FileStatus = importItem ? 'processing' : status
    return <Badge className={statusStyles[shown]}>{statusLabels[shown]}</Badge>
}
