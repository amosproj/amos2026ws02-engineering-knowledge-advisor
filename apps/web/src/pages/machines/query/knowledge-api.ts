import { queryOptions } from '@tanstack/react-query'
import { z } from 'zod'

import { queryMaker } from '@queries/query-maker'

import { machinesQueryKey } from './machine-api'

export const ITEM_TYPES = [
    'requirement',
    'consideration',
    'design decision',
    'lesson learned',
] as const

export const CONFIDENCE_LEVELS = ['established practice', 'rule of thumb', 'unverified'] as const

export const DETAIL_FIELDS = ['reasoning', 'condition', 'consequence', 'recommendation'] as const

const itemType = z.enum(ITEM_TYPES)
const confidence = z.enum(CONFIDENCE_LEVELS)

const knowledgePropertiesSchema = z.looseObject({
    statement: z.string(),
    name: z.string().optional(),
    reasoning: z.string().optional(),
    condition: z.string().optional(),
    consequence: z.string().optional(),
    recommendation: z.string().optional(),
    confidence: confidence.optional(),
})

const knowledgeItemSchema = z.looseObject({
    '@id': z.string(),
    itemType: itemType.optional(),
    reference: z.string().optional(),
    properties: knowledgePropertiesSchema,
})

const knowledgeItemViewSchema = z.object({
    record: knowledgeItemSchema,
    version: z.string(),
})

const writtenSchema = z.object({
    id: z.string(),
    warnings: z.array(z.string()),
    version: z.string(),
})

const knowledgeItemBody = z.object({
    '@type': z.literal('KnowledgeItem'),
    itemType: itemType.optional(),
    reference: z.string().optional(),
    properties: z.object({
        statement: z.string(),
        name: z.string().optional(),
        reasoning: z.string().optional(),
        condition: z.string().optional(),
        consequence: z.string().optional(),
        recommendation: z.string().optional(),
        confidence: confidence.optional(),
    }),
    appliesToInstance: z.string(),
})

// JSON Merge Patch: null removes a value, nested properties merge key by key
const knowledgeItemChanges = z.object({
    itemType: itemType.nullable(),
    reference: z.string().nullable(),
    properties: z.object({
        statement: z.string(),
        name: z.string().nullable(),
        reasoning: z.string().nullable(),
        condition: z.string().nullable(),
        consequence: z.string().nullable(),
        recommendation: z.string().nullable(),
        confidence: confidence.nullable(),
    }),
})

export type ItemType = z.output<typeof itemType>
export type Confidence = z.output<typeof confidence>
export type DetailField = (typeof DETAIL_FIELDS)[number]
export type KnowledgeItemView = z.output<typeof knowledgeItemViewSchema>
export type KnowledgeItemBody = z.input<typeof knowledgeItemBody>
export type KnowledgeItemChanges = z.input<typeof knowledgeItemChanges>

const idParams = z.object({ id: z.string() })

export const listKnowledgeItems = queryMaker({
    method: 'GET',
    path: '/v1/records',
    search: z.object({
        cls: z.literal('KnowledgeItem'),
        parentId: z.string(),
        include: z.literal('children'),
    }),
    response: z.array(knowledgeItemViewSchema),
})

export const createKnowledgeItem = queryMaker({
    method: 'POST',
    path: '/v1/records',
    body: knowledgeItemBody,
    response: writtenSchema,
})

export const updateKnowledgeItem = queryMaker({
    method: 'PATCH',
    path: '/v1/records/:id',
    params: idParams,
    body: knowledgeItemChanges,
    response: writtenSchema,
})

export const deleteKnowledgeItem = queryMaker({
    method: 'DELETE',
    path: '/v1/records/:id',
    params: idParams,
    response: z.object({ deletedIds: z.array(z.string()), markedIds: z.array(z.string()) }),
})

export const knowledgeItemsQueryKey = (instanceId: string) =>
    [...machinesQueryKey, 'knowledge', instanceId] as const

export const knowledgeItemsQuery = (instanceId: string) =>
    queryOptions({
        queryKey: knowledgeItemsQueryKey(instanceId),
        queryFn: ({ signal }) =>
            listKnowledgeItems({
                search: { cls: 'KnowledgeItem', parentId: instanceId, include: 'children' },
                signal,
            }),
    })
