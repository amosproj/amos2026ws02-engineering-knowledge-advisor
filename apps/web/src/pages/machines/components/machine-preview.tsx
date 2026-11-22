import { useState } from 'react'
import { EngineIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import { previewUrl } from '../query/machine-api'

export function MachinePreview({ cadFileId }: { cadFileId: string | undefined }) {
    const [failed, setFailed] = useState(false)

    return (
        <div className="flex aspect-4/3 w-28 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-neutral-200 dark:bg-neutral-700">
            {cadFileId !== undefined && !failed ? (
                <img
                    src={previewUrl(cadFileId)}
                    alt=""
                    loading="lazy"
                    className="size-full object-contain"
                    onError={() => setFailed(true)}
                />
            ) : (
                <HugeiconsIcon
                    icon={EngineIcon}
                    strokeWidth={1.5}
                    className="text-muted-foreground/50 size-8"
                />
            )}
        </div>
    )
}
