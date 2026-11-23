import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useStore } from '@tanstack/react-form'

import { Badge, FieldGroup, NativeSelectOption, toast, useAppForm } from '@components'

import {
    FIELD_HINTS,
    FIELD_LABELS,
    knowledgeFormSchema,
    newKnowledgeForm,
    toKnowledgeBody,
    toKnowledgeChanges,
    toKnowledgeForm,
    type Bucket,
    type KnowledgeForm,
} from '../models/knowledge-model'
import { errorMessage, isStale } from '../models/machine-errors'
import {
    CONFIDENCE_LEVELS,
    DETAIL_FIELDS,
    ITEM_TYPES,
    createKnowledgeItem,
    knowledgeItemsQueryKey,
    updateKnowledgeItem,
    type KnowledgeItemView,
} from '../query/knowledge-api'
import { DialogForm, FormDialog, FormDialogFooter, type FormDialogControls } from './form-dialog'

type KnowledgeFormDialogProps = {
    instanceId: string
    // Edited item, a new item without it
    item?: KnowledgeItemView
    // Bucket a new item starts from
    bucket?: Bucket
    open: boolean
    onOpenChange: (open: boolean) => void
}

export function KnowledgeFormDialog({
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
                                            labelAction={<Badge variant="outline">Required</Badge>}
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
                                        description={FIELD_HINTS.name}
                                        autoComplete="off"
                                    />
                                )}
                            </form.AppField>
                            <form.AppField name="itemType">
                                {(field) => (
                                    <field.NativeSelectForm label={FIELD_LABELS.itemType}>
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
                                            description={FIELD_HINTS[key]}
                                            rows={2}
                                        />
                                    )}
                                </form.AppField>
                            ))}
                            <form.AppField name="confidence">
                                {(field) => (
                                    <field.NativeSelectForm
                                        label={FIELD_LABELS.confidence}
                                        description={FIELD_HINTS.confidence}
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
                                        description={FIELD_HINTS.reference}
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
