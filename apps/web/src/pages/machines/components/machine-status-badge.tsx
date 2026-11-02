import { cn } from 'cn'

import { Badge } from '@components'

import type { MachineStatus } from '../query/machine-api'
import type { ActiveImport } from './machine-import-context'

const statusStyles: Record<MachineStatus, string> = {
    uploading: 'bg-secondary text-secondary-foreground',
    processing: 'hazard-stripes animate-hazard text-hazard-foreground motion-reduce:animate-none',
    ready: 'bg-success/15 text-success',
    failed: 'bg-destructive/10 text-destructive dark:bg-destructive/20',
}

const statusLabels: Record<MachineStatus, string> = {
    uploading: 'Uploading',
    processing: 'Processing',
    ready: 'Ready',
    failed: 'Failed',
}

type MachineStatusBadgeProps = {
    status: MachineStatus
    // The import running in this tab is ahead of the list, it also knows the upload progress
    activeImport?: ActiveImport | null
}

export function MachineStatusBadge({ status, activeImport }: MachineStatusBadgeProps) {
    const shownStatus = activeImport?.phase ?? status

    return (
        <Badge className={cn('tabular-nums', statusStyles[shownStatus])}>
            {statusLabels[shownStatus]}
            {activeImport?.phase === 'uploading' ? ` ${activeImport.percent} %` : null}
        </Badge>
    )
}
