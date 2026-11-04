import { cn } from 'cn'

import { Badge } from '@components'

import type { CadFileStatus, MachineStatus } from '../query/machine-api'
import type { ImportItem } from './cad-file-import-context'

type Status = MachineStatus | CadFileStatus | 'queued'

const statusStyles: Record<Status, string> = {
    empty: 'bg-muted text-muted-foreground',
    queued: 'bg-secondary text-secondary-foreground',
    uploading: 'bg-secondary text-secondary-foreground',
    processing: 'hazard-stripes animate-hazard text-hazard-foreground motion-reduce:animate-none',
    ready: 'bg-success/15 text-success',
    failed: 'bg-destructive/10 text-destructive dark:bg-destructive/20',
}

const statusLabels: Record<Status, string> = {
    empty: 'Empty',
    queued: 'Queued',
    uploading: 'Uploading',
    processing: 'Processing',
    ready: 'Ready',
    failed: 'Failed',
}

type StatusBadgeProps = {
    status: MachineStatus | CadFileStatus
    // The import running in this tab is ahead of the server, it also knows the upload progress
    importItem?: ImportItem
}

export function StatusBadge({ status, importItem }: StatusBadgeProps) {
    const phase = importItem?.phase
    const shownStatus: Status =
        phase === 'queued' || phase === 'uploading' || phase === 'processing' ? phase : status

    return (
        <Badge className={cn('tabular-nums', statusStyles[shownStatus])}>
            {statusLabels[shownStatus]}
            {phase === 'uploading' ? ` ${importItem?.percent} %` : null}
        </Badge>
    )
}
