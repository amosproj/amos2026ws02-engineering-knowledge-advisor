import { Cancel01Icon, Upload04Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Button,
    Popover,
    PopoverContent,
    PopoverDescription,
    PopoverHeader,
    PopoverTitle,
    PopoverTrigger,
    Progress,
} from '@components'

import { isCancellable, useCadFileImport, type ImportItem } from './cad-file-import-context'

const phaseLabels: Record<ImportItem['phase'], string> = {
    queued: 'Waiting',
    uploading: 'Uploading',
    processing: 'Processing',
    ready: 'Ready',
    failed: 'Failed',
    cancelled: 'Cancelled',
    processing_timeout: 'Still processing on the server',
}

/** Header button that follows the imports of this tab, hidden when none runs. */
export function ImportIndicator() {
    const { items, cancelImport } = useCadFileImport()
    if (items.length === 0) return null

    const uploads = items.filter((item) => item.phase !== 'cancelled')
    const totalBytes = uploads.reduce((sum, item) => sum + item.size, 0)
    const sentBytes = uploads.reduce((sum, item) => sum + (item.size * item.percent) / 100, 0)
    const percent = totalBytes ? Math.floor((sentBytes / totalBytes) * 100) : 100
    const uploaded = items.filter((item) => !isCancellable(item)).length

    return (
        <Popover>
            <PopoverTrigger
                render={
                    <Button variant="secondary" className="relative min-w-36 overflow-hidden" />
                }
            >
                <span
                    aria-hidden="true"
                    className="bg-primary/25 absolute inset-y-0 left-0 transition-[width]"
                    style={{ width: `${percent}%` }}
                />
                <HugeiconsIcon icon={Upload04Icon} strokeWidth={2} data-icon="inline-start" />
                <span className="relative tabular-nums">
                    Import {uploaded}/{items.length} · {percent} %
                </span>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-96">
                <PopoverHeader>
                    <PopoverTitle>STEP file import</PopoverTitle>
                    <PopoverDescription>
                        Keep this tab open until the files are uploaded.
                    </PopoverDescription>
                </PopoverHeader>
                <ul className="flex flex-col gap-3">
                    {items.map((item) => (
                        <li key={item.cadFileId} className="flex items-start gap-2">
                            <div className="flex min-w-0 flex-1 flex-col gap-1">
                                <p className="truncate text-sm font-medium">{item.name}</p>
                                {item.phase === 'uploading' ? (
                                    <Progress
                                        value={item.percent}
                                        aria-label={`Upload of ${item.name}`}
                                    >
                                        <span className="text-muted-foreground text-xs tabular-nums">
                                            Uploading {item.percent} %
                                        </span>
                                    </Progress>
                                ) : (
                                    <p
                                        className={
                                            item.phase === 'failed'
                                                ? 'text-destructive text-xs'
                                                : 'text-muted-foreground text-xs'
                                        }
                                    >
                                        {item.message ?? phaseLabels[item.phase]}
                                    </p>
                                )}
                            </div>
                            {isCancellable(item) ? (
                                <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    aria-label={`Cancel the upload of ${item.name}`}
                                    onClick={() => cancelImport(item.cadFileId)}
                                >
                                    <HugeiconsIcon icon={Cancel01Icon} strokeWidth={2} />
                                </Button>
                            ) : null}
                        </li>
                    ))}
                </ul>
            </PopoverContent>
        </Popover>
    )
}
