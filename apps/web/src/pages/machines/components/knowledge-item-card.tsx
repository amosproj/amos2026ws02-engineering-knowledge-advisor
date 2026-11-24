import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { Badge, ConfirmationPopup, toast } from '@components'

import { FIELD_LABELS, knowledgeDetails } from '../models/knowledge-model'
import { errorMessage } from '../models/machine-errors'
import {
    deleteKnowledgeItem,
    knowledgeItemsQueryKey,
    type KnowledgeItemView,
} from '../query/knowledge-api'
import { ActionsMenu } from './actions-menu'
import { KnowledgeFormDialog } from './knowledge-form-dialog'

type KnowledgeItemCardProps = {
    item: KnowledgeItemView
    instanceId: string
}

export function KnowledgeItemCard({ item, instanceId }: KnowledgeItemCardProps) {
    const { record } = item
    const [editing, setEditing] = useState(false)
    const [deleting, setDeleting] = useState(false)
    const details = knowledgeDetails(item)

    const remove = useMutation({
        mutationFn: () => deleteKnowledgeItem({ params: { id: record['@id'] } }),
        meta: { invalidates: [knowledgeItemsQueryKey(instanceId)], invalidateOnError: true },
        onSuccess: () => toast.add({ type: 'success', title: 'Knowledge deleted' }),
        onError: (error) =>
            toast.add({ type: 'error', title: 'Delete failed', description: errorMessage(error) }),
    })

    return (
        <li className="grid gap-1.5 rounded-lg border p-3">
            <div className="flex items-start justify-between gap-2">
                <div className="grid min-w-0 gap-0.5">
                    {record.properties.name ? (
                        <p className="font-medium wrap-anywhere">{record.properties.name}</p>
                    ) : null}
                    <p className="wrap-anywhere whitespace-pre-wrap">
                        {record.properties.statement}
                    </p>
                </div>
                <ActionsMenu
                    label="Actions of this knowledge"
                    size="icon-sm"
                    actions={[
                        { label: 'Edit', onSelect: () => setEditing(true) },
                        {
                            label: 'Delete',
                            onSelect: () => setDeleting(true),
                            destructive: true,
                            disabled: remove.isPending,
                        },
                    ]}
                />
            </div>
            {details.length > 0 || record.reference ? (
                <dl className="grid gap-1 text-xs">
                    {details.map((detail) => (
                        <div key={detail.key} className="grid grid-cols-[7.5rem_1fr] gap-x-2">
                            <dt className="text-muted-foreground">{detail.label}</dt>
                            <dd className="min-w-0 wrap-anywhere whitespace-pre-wrap">
                                {detail.value}
                            </dd>
                        </div>
                    ))}
                    {record.reference ? (
                        <div className="grid grid-cols-[7.5rem_1fr] gap-x-2">
                            <dt className="text-muted-foreground">{FIELD_LABELS.reference}</dt>
                            <dd className="min-w-0 wrap-anywhere">{record.reference}</dd>
                        </div>
                    ) : null}
                </dl>
            ) : null}
            {record.itemType || record.properties.confidence ? (
                <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
                    {record.itemType ? <Badge variant="secondary">{record.itemType}</Badge> : null}
                    {record.properties.confidence ? (
                        <Badge variant="outline">{record.properties.confidence}</Badge>
                    ) : null}
                </div>
            ) : null}
            <KnowledgeFormDialog
                instanceId={instanceId}
                item={item}
                open={editing}
                onOpenChange={setEditing}
            />
            <ConfirmationPopup
                open={deleting}
                onOpenChange={setDeleting}
                title="Delete this knowledge?"
                description="It is permanently deleted."
                confirmLabel="Delete knowledge"
                cancelLabel="Keep knowledge"
                onConfirm={() => remove.mutate()}
            />
        </li>
    )
}
