import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useStore } from '@tanstack/react-form'
import { Add01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Badge,
    Button,
    ConfirmationPopup,
    FieldGroup,
    NativeSelectOption,
    Skeleton,
    toast,
    useAppForm,
} from '@components'

import {
    FIELD_HINTS,
    FIELD_LABELS,
    knowledgeDetails,
    knowledgeFormSchema,
    newKnowledgeForm,
    toKnowledgeBody,
    toKnowledgeChanges,
    toKnowledgeForm,
    unusedBuckets,
    type Bucket,
    type KnowledgeForm,
} from '../models/knowledge-model'
import { errorMessage, isStale } from '../models/machine-errors'
import {
    CONFIDENCE_LEVELS,
    DETAIL_FIELDS,
    ITEM_TYPES,
    createKnowledgeItem,
    deleteKnowledgeItem,
    knowledgeItemsQuery,
    knowledgeItemsQueryKey,
    updateKnowledgeItem,
    type KnowledgeItemView,
} from '../query/knowledge-api'
import { ActionsMenu } from './actions-menu'
import { DialogForm, FormDialog, FormDialogFooter, type FormDialogControls } from './form-dialog'

type KnowledgeItemsProps = {
    // The assembly instance (tree node) the knowledge belongs to
    instanceId: string
    instanceName: string
}

export function KnowledgeItems({ instanceId, instanceName }: KnowledgeItemsProps) {
    const items = useQuery(knowledgeItemsQuery(instanceId))
    const [adding, setAdding] = useState(false)
    // Bucket the new item starts from, none for a blank one. Kept while the dialog closes.
    const [bucket, setBucket] = useState<Bucket>()

    const buckets: Bucket[] = items.isSuccess ? unusedBuckets(items.data) : []

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
            {buckets.length > 0 ? (
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
                                    onClick={() => add(entry)}
                                >
                                    {entry.name}
                                </Button>
                            </li>
                        ))}
                    </ul>
                </div>
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

type KnowledgeItemCardProps = {
    item: KnowledgeItemView
    instanceId: string
}

function KnowledgeItemCard({ item, instanceId }: KnowledgeItemCardProps) {
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

type KnowledgeFormDialogProps = {
    instanceId: string
    // Edited item, a new item without it
    item?: KnowledgeItemView
    // Bucket a new item starts from
    bucket?: Bucket
    open: boolean
    onOpenChange: (open: boolean) => void
}

function KnowledgeFormDialog({
    instanceId,
    item,
    bucket,
    open,
    onOpenChange,
}: KnowledgeFormDialogProps) {
    return (
        <FormDialog
            title={item ? 'Edit knowledge' : 'Add knowledge'}
            description="Write the knowledge in one or two sentences, as you would tell a colleague."
            open={open}
            onOpenChange={onOpenChange}
            wide
        >
            {(dialog) => (
                <KnowledgeFormBody
                    instanceId={instanceId}
                    item={item}
                    bucket={item ? undefined : bucket}
                    dialog={dialog}
                />
            )}
        </FormDialog>
    )
}

type KnowledgeFormBodyProps = {
    instanceId: string
    item?: KnowledgeItemView
    bucket?: Bucket
    dialog: FormDialogControls
}

function KnowledgeFormBody({ instanceId, item, bucket, dialog }: KnowledgeFormBodyProps) {
    const queryClient = useQueryClient()
    const [error, setError] = useState<string | null>(null)
    // Version of the form values: a refetch while editing must not hide a concurrent save
    const [version] = useState(item?.version)

    const refresh = () =>
        void queryClient.invalidateQueries({ queryKey: knowledgeItemsQueryKey(instanceId) })

    const save = async (value: KnowledgeForm) => {
        if (item) {
            await updateKnowledgeItem({
                params: { id: item.record['@id'] },
                headers: { 'If-Match': `"${version}"` },
                body: toKnowledgeChanges(value),
            })
        } else {
            await createKnowledgeItem({ body: toKnowledgeBody(value, instanceId) })
        }
    }

    const form = useAppForm({
        defaultValues: item ? toKnowledgeForm(item) : newKnowledgeForm(bucket),
        validators: { onSubmit: knowledgeFormSchema },
        onSubmit: async ({ value }) => {
            setError(null)
            dialog.setBusy(true)
            try {
                await save(knowledgeFormSchema.parse(value))
                refresh()
                dialog.close()
                toast.add({ type: 'success', title: item ? 'Knowledge saved' : 'Knowledge added' })
            } catch (saveError) {
                if (isStale(saveError)) {
                    refresh()
                    setError('Someone changed this knowledge meanwhile. Close and open it again.')
                } else {
                    setError(errorMessage(saveError))
                }
            } finally {
                dialog.setBusy(false)
            }
        },
    })

    // Input that differs from what the dialog opened with
    const unsaved = useStore(form.store, (state) => !state.isDefaultValue)
    const { setUnsaved } = dialog
    useEffect(() => setUnsaved(unsaved), [unsaved, setUnsaved])

    return (
        <form.AppForm>
            <form.Subscribe selector={(state) => state.isSubmitting}>
                {(isSubmitting) => (
                    <DialogForm onSubmit={() => void form.handleSubmit()} submitting={isSubmitting}>
                        {/* Two columns from sm up: the knowledge spans both, the details pair up */}
                        <FieldGroup className="grid items-start gap-x-6 gap-y-5 sm:grid-cols-2">
                            <div className="sm:col-span-2">
                                <form.AppField name="statement">
                                    {(field) => (
                                        <field.TextareaForm
                                            label={FIELD_LABELS.statement}
                                            placeholder={
                                                bucket?.example ??
                                                'e.g. Chamfer the nest so parts slide in without jamming.'
                                            }
                                            rows={3}
                                        />
                                    )}
                                </form.AppField>
                            </div>
                            <form.AppField name="name">
                                {(field) => (
                                    <field.InputForm
                                        label={FIELD_LABELS.name}
                                        description={`${FIELD_HINTS.name} Optional.`}
                                        autoComplete="off"
                                    />
                                )}
                            </form.AppField>
                            <form.AppField name="itemType">
                                {(field) => (
                                    <field.NativeSelectForm
                                        label={FIELD_LABELS.itemType}
                                        description="Optional."
                                    >
                                        <NativeSelectOption value="">No type</NativeSelectOption>
                                        {ITEM_TYPES.map((type) => (
                                            <NativeSelectOption key={type} value={type}>
                                                {type}
                                            </NativeSelectOption>
                                        ))}
                                    </field.NativeSelectForm>
                                )}
                            </form.AppField>
                            {DETAIL_FIELDS.map((key) => (
                                <form.AppField key={key} name={key}>
                                    {(field) => (
                                        <field.TextareaForm
                                            label={FIELD_LABELS[key]}
                                            description={`${FIELD_HINTS[key]} Optional.`}
                                            rows={2}
                                        />
                                    )}
                                </form.AppField>
                            ))}
                            <form.AppField name="confidence">
                                {(field) => (
                                    <field.NativeSelectForm
                                        label={FIELD_LABELS.confidence}
                                        description={`${FIELD_HINTS.confidence} Optional.`}
                                    >
                                        <NativeSelectOption value="">Not set</NativeSelectOption>
                                        {CONFIDENCE_LEVELS.map((level) => (
                                            <NativeSelectOption key={level} value={level}>
                                                {level}
                                            </NativeSelectOption>
                                        ))}
                                    </field.NativeSelectForm>
                                )}
                            </form.AppField>
                            <form.AppField name="reference">
                                {(field) => (
                                    <field.InputForm
                                        label={FIELD_LABELS.reference}
                                        description={`${FIELD_HINTS.reference} Optional.`}
                                        autoComplete="off"
                                    />
                                )}
                            </form.AppField>
                        </FieldGroup>
                        <FormDialogFooter
                            error={error}
                            submitLabel={item ? 'Save' : 'Add'}
                            onCancel={dialog.cancel}
                        />
                    </DialogForm>
                )}
            </form.Subscribe>
        </form.AppForm>
    )
}
