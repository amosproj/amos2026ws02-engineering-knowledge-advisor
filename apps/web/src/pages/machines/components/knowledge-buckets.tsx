import { Button } from '@components'

import { unusedBuckets, type Bucket } from '../models/knowledge-model'
import type { KnowledgeItemView } from '../query/knowledge-api'

type KnowledgeBucketsProps = {
    instanceId: string
    items: KnowledgeItemView[]
    onSelect: (bucket: Bucket) => void
}

export function KnowledgeBuckets({ instanceId, items, onSelect }: KnowledgeBucketsProps) {
    const buckets: Bucket[] = unusedBuckets(items)
    if (buckets.length === 0) return null

    return (
        <div className="flex flex-wrap items-center gap-1.5">
            <span id={`buckets-${instanceId}`} className="text-muted-foreground text-xs">
                Start from a bucket
            </span>
            <ul aria-labelledby={`buckets-${instanceId}`} className="contents">
                {buckets.map((entry) => (
                    <li key={entry.name}>
                        <Button
                            variant="secondary"
                            size="xs"
                            className="rounded-full"
                            onClick={() => onSelect(entry)}
                        >
                            {entry.name}
                        </Button>
                    </li>
                ))}
            </ul>
        </div>
    )
}
