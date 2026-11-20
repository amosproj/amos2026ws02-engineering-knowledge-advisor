import { z } from 'zod'

import {
    CONFIDENCE_LEVELS,
    DETAIL_FIELDS,
    ITEM_TYPES,
    type KnowledgeItemBody,
    type KnowledgeItemChanges,
    type ItemType,
    type KnowledgeItemView,
} from '../query/knowledge-api'

export const STATEMENT_MAX_LENGTH = 2000
const DETAIL_MAX_LENGTH = 2000
const SHORT_MAX_LENGTH = 255

const optionalText = (label: string, max: number) =>
    z.string().trim().max(max, `The ${label} must be ${max} characters or fewer.`)

/** Labels of the knowledge properties, as the ontology names them. */
export const FIELD_LABELS = {
    name: 'Name',
    statement: 'Statement',
    reasoning: 'Reasoning',
    condition: 'Condition',
    consequence: 'Consequence',
    recommendation: 'Recommendation',
    confidence: 'Confidence',
    itemType: 'Type',
    reference: 'Reference',
} as const

/** Help text from the ontology comments. */
export const FIELD_HINTS = {
    name: 'Short name of the item.',
    reasoning: 'Why the knowledge holds: the engineering reasoning behind it.',
    condition: 'When it applies, e.g. a part size or an operating case.',
    consequence: 'What happens when it is ignored.',
    recommendation: 'What to do, according to it.',
    confidence: 'How well established the knowledge is.',
    reference: 'A standard, norm or other source, e.g. DIN EN ISO 13849.',
} as const

/** A predefined start for new knowledge: its name, and an example statement. */
export type Bucket = {
    name: string
    example: string
}

/** Basic buckets: global properties of a machine, offered on every element. */
export const BUCKETS: readonly Bucket[] = [
    { name: 'Size of product produced', example: 'e.g. Parts up to 200 × 150 × 80 mm and 2 kg.' },
    { name: 'Cycle time of system', example: 'e.g. 45 s per part, one part at a time.' },
    {
        name: 'Variance in product',
        example: 'e.g. 12 part variants, changed by the operator without tools.',
    },
    {
        name: 'Production environment',
        example: 'e.g. Workshop at 15–30 °C, dusty, compressed air available.',
    },
    {
        name: 'Used manufacturing processes',
        example: 'e.g. 3D printing, then support removal by chiselling.',
    },
    {
        name: 'Process flow description',
        example:
            'e.g. The operator loads the drawer, the robot picks, processes and returns the part.',
    },
    {
        name: 'Safety aspects',
        example: 'e.g. Fenced cell with door interlock, PL d per DIN EN ISO 13849.',
    },
    {
        name: 'User experience',
        example: 'e.g. The operator loads at hip height and sees the status from the front.',
    },
]

/** The buckets no item of ``items`` is named after yet. */
export function unusedBuckets(items: readonly KnowledgeItemView[]): Bucket[] {
    const used = new Set(items.map((item) => item.record.properties.name?.trim()))
    return BUCKETS.filter((bucket) => !used.has(bucket.name))
}

/** Machine properties are requirements on the machine. */
const BUCKET_ITEM_TYPE: ItemType = 'requirement'

export const knowledgeFormSchema = z.object({
    statement: z
        .string()
        .trim()
        .min(1, 'Enter the statement.')
        .max(
            STATEMENT_MAX_LENGTH,
            `The statement must be ${STATEMENT_MAX_LENGTH} characters or fewer.`,
        ),
    name: optionalText('name', SHORT_MAX_LENGTH),
    reasoning: optionalText('reasoning', DETAIL_MAX_LENGTH),
    condition: optionalText('condition', DETAIL_MAX_LENGTH),
    consequence: optionalText('consequence', DETAIL_MAX_LENGTH),
    recommendation: optionalText('recommendation', DETAIL_MAX_LENGTH),
    // Empty: not set
    confidence: z.enum(['', ...CONFIDENCE_LEVELS]),
    itemType: z.enum(['', ...ITEM_TYPES]),
    reference: optionalText('reference', SHORT_MAX_LENGTH),
})

export type KnowledgeForm = z.output<typeof knowledgeFormSchema>

export function toKnowledgeForm(item: KnowledgeItemView | undefined): KnowledgeForm {
    const properties = item?.record.properties
    return {
        statement: properties?.statement ?? '',
        name: properties?.name ?? '',
        reasoning: properties?.reasoning ?? '',
        condition: properties?.condition ?? '',
        consequence: properties?.consequence ?? '',
        recommendation: properties?.recommendation ?? '',
        confidence: properties?.confidence ?? '',
        itemType: item?.record.itemType ?? '',
        reference: item?.record.reference ?? '',
    }
}

/** A new item, started from ``bucket``: named after it, as a requirement. */
export function newKnowledgeForm(bucket: Bucket | undefined): KnowledgeForm {
    const empty = toKnowledgeForm(undefined)
    return bucket ? { ...empty, name: bucket.name, itemType: BUCKET_ITEM_TYPE } : empty
}

/** A new item: empty values are left out. */
export function toKnowledgeBody(form: KnowledgeForm, instanceId: string): KnowledgeItemBody {
    const set = <K extends string, V>(key: K, value: V | '') =>
        (value ? { [key]: value } : {}) as Partial<Record<K, V>>
    return {
        '@type': 'KnowledgeItem',
        ...set('itemType', form.itemType),
        ...set('reference', form.reference),
        properties: {
            statement: form.statement,
            ...set('name', form.name),
            ...Object.assign({}, ...DETAIL_FIELDS.map((key) => set(key, form[key]))),
            ...set('confidence', form.confidence),
        },
        appliesToInstance: instanceId,
    }
}

/** Merge patch: a cleared value is sent as null, which removes it. */
export function toKnowledgeChanges(form: KnowledgeForm): KnowledgeItemChanges {
    return {
        itemType: form.itemType || null,
        reference: form.reference || null,
        properties: {
            statement: form.statement,
            name: form.name || null,
            reasoning: form.reasoning || null,
            condition: form.condition || null,
            consequence: form.consequence || null,
            recommendation: form.recommendation || null,
            confidence: form.confidence || null,
        },
    }
}

/** The filled detail properties of an item, in display order. */
export function knowledgeDetails(item: KnowledgeItemView) {
    const { properties } = item.record
    return DETAIL_FIELDS.flatMap((key) => {
        const value = properties[key]
        return value ? [{ key, label: FIELD_LABELS[key], value }] : []
    })
}
