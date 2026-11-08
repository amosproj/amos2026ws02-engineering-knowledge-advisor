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

import { useCadFileImport } from './cad-file-import-context'

export function ImportIndicator() {
    const { items, cancelImport } = useCadFileImport()
    if (items.length === 0) return null

    const totalBytes = items.reduce((sum, item) => sum + item.size, 0)
    const sentBytes = items.reduce((sum, item) => sum + (item.size * item.percent) / 100, 0)
    const percent = totalBytes ? Math.floor((sentBytes / totalBytes) * 100) : 100

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
                    {items.length === 1 ? 'Upload' : `${items.length} uploads`} · {percent} %
                </span>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-96">
                <PopoverHeader>
                    <PopoverTitle>CAD file uploads</PopoverTitle>
                    <PopoverDescription>
                        Keep this tab open until the files are uploaded.
                    </PopoverDescription>
                </PopoverHeader>
                <ul className="flex flex-col gap-3">
                    {items.map((item) => (
                        <li key={item.machineId} className="flex items-start gap-2">
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
                                    <p className="text-muted-foreground text-xs">Processing</p>
                                )}
                            </div>
                            {item.phase === 'uploading' ? (
                                <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    aria-label={`Cancel the upload of ${item.name}`}
                                    onClick={() => cancelImport(item.machineId)}
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
