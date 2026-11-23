import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Add01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import { Button, Skeleton } from '@components'

import type { Bucket } from '../models/knowledge-model'
import { knowledgeItemsQuery } from '../query/knowledge-api'
import { KnowledgeBuckets } from './knowledge-buckets'
import { KnowledgeFormDialog } from './knowledge-form-dialog'
import { KnowledgeItemCard } from './knowledge-item-card'

type KnowledgeItemsProps = {
    instanceId: string
    instanceName: string
}

export function KnowledgeItems({ instanceId, instanceName }: KnowledgeItemsProps) {
    const items = useQuery(knowledgeItemsQuery(instanceId))
    const [adding, setAdding] = useState(false)
    const [bucket, setBucket] = useState<Bucket>()

    const add = (from?: Bucket) => {
        setBucket(from)
        setAdding(true)
    }

    return (
        <section className="mt-2 grid gap-2" aria-labelledby={`knowledge-${instanceId}`}>
            <div className="flex items-center justify-between gap-2">
                <h3 id={`knowledge-${instanceId}`} className="font-medium">
                    Knowledge
                </h3>
                <Button variant="outline" size="sm" onClick={() => add()}>
                    <HugeiconsIcon icon={Add01Icon} strokeWidth={2} />
                    Add knowledge
                </Button>
            </div>
            {/* Shown once the items are known, so a used bucket never flashes up */}
            {items.isSuccess ? (
                <KnowledgeBuckets
                    instanceId={instanceId}
                    items={items.data}
                    onSelect={(entry) => add(entry)}
                />
            ) : null}
            {items.isPending ? (
                <div className="grid gap-2">
                    <Skeleton className="h-16" />
                    <Skeleton className="h-16" />
                </div>
            ) : items.isError ? (
                <div className="grid gap-2">
                    <p className="text-destructive">The knowledge could not be loaded.</p>
                    <Button
                        variant="outline"
                        size="sm"
                        className="justify-self-start"
                        onClick={() => void items.refetch()}
                    >
                        Try again
                    </Button>
                </div>
            ) : items.data.length === 0 ? (
                <p className="text-muted-foreground rounded-lg border border-dashed p-4 text-center">
                    No knowledge about {instanceName} yet.
                </p>
            ) : (
                <ul className="grid gap-2">
                    {items.data.map((item) => (
                        <KnowledgeItemCard
                            key={item.record['@id']}
                            item={item}
                            instanceId={instanceId}
                        />
                    ))}
                </ul>
            )}
            <KnowledgeFormDialog
                instanceId={instanceId}
                bucket={bucket}
                open={adding}
                onOpenChange={setAdding}
            />
        </section>
    )
}
