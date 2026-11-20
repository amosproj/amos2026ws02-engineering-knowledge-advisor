import { describe, expect, it } from 'vitest'

import type { KnowledgeItemView } from '../query/knowledge-api'
import {
    knowledgeDetails,
    BUCKETS,
    knowledgeFormSchema,
    newKnowledgeForm,
    unusedBuckets,
    toKnowledgeBody,
    toKnowledgeChanges,
    toKnowledgeForm,
    type KnowledgeForm,
} from './knowledge-model'

function item(id: string): KnowledgeItemView {
    return {
        record: { '@id': id, properties: { statement: `Text ${id}` } },
        version: '1',
    }
}

const EMPTY: KnowledgeForm = {
    statement: '',
    name: '',
    reasoning: '',
    condition: '',
    consequence: '',
    recommendation: '',
    confidence: '',
    itemType: '',
    reference: '',
}

describe('knowledgeFormSchema', () => {
    it('refuses blank knowledge', () => {
        const parsed = knowledgeFormSchema.safeParse({ ...EMPTY, statement: '   ' })

        expect(parsed.success).toBe(false)
    })

    it('trims the knowledge and the details', () => {
        const parsed = knowledgeFormSchema.parse({
            ...EMPTY,
            statement: '  Chamfer the nest. ',
            reasoning: ' Parts jam. ',
        })

        expect(parsed.statement).toBe('Chamfer the nest.')
        expect(parsed.reasoning).toBe('Parts jam.')
    })
})

describe('toKnowledgeBody', () => {
    it('links the item to the instance and leaves out empty values', () => {
        const body = toKnowledgeBody({ ...EMPTY, statement: 'Chamfer the nest.' }, 'AI-1')

        expect(body).toEqual({
            '@type': 'KnowledgeItem',
            properties: { statement: 'Chamfer the nest.' },
            appliesToInstance: 'AI-1',
        })
    })

    it('puts the knowledge properties in properties and the rest on the item', () => {
        const body = toKnowledgeBody(
            {
                statement: 'Chamfer the nest.',
                name: 'Nest chamfer',
                reasoning: 'Parts jam on sharp edges.',
                condition: 'Parts under 5 mm',
                consequence: 'Line stops',
                recommendation: 'Chamfer 0.5 mm',
                confidence: 'rule of thumb',
                itemType: 'lesson learned',
                reference: 'DIN EN ISO 13849',
            },
            'AI-1',
        )

        expect(body).toEqual({
            '@type': 'KnowledgeItem',
            itemType: 'lesson learned',
            reference: 'DIN EN ISO 13849',
            properties: {
                statement: 'Chamfer the nest.',
                name: 'Nest chamfer',
                reasoning: 'Parts jam on sharp edges.',
                condition: 'Parts under 5 mm',
                consequence: 'Line stops',
                recommendation: 'Chamfer 0.5 mm',
                confidence: 'rule of thumb',
            },
            appliesToInstance: 'AI-1',
        })
    })
})

describe('toKnowledgeChanges', () => {
    it('removes cleared values with null', () => {
        expect(toKnowledgeChanges({ ...EMPTY, statement: 'X' })).toEqual({
            itemType: null,
            reference: null,
            properties: {
                statement: 'X',
                name: null,
                reasoning: null,
                condition: null,
                consequence: null,
                recommendation: null,
                confidence: null,
            },
        })
    })
})

describe('toKnowledgeForm', () => {
    it('starts empty for a new item and from the item when editing', () => {
        expect(toKnowledgeForm(undefined)).toEqual(EMPTY)
        const edited = item('KI-1')
        edited.record.itemType = 'requirement'
        edited.record.reference = 'VDI 2221'
        edited.record.properties.confidence = 'unverified'
        edited.record.properties.condition = 'Wet parts'

        expect(toKnowledgeForm(edited)).toEqual({
            ...EMPTY,
            statement: 'Text KI-1',
            itemType: 'requirement',
            reference: 'VDI 2221',
            confidence: 'unverified',
            condition: 'Wet parts',
        })
    })
})

describe('newKnowledgeForm', () => {
    it('names a new item after its bucket, as a requirement', () => {
        expect(newKnowledgeForm(BUCKETS[1])).toEqual({
            ...EMPTY,
            name: 'Cycle time of system',
            itemType: 'requirement',
        })
    })

    it('starts empty without a bucket', () => {
        expect(newKnowledgeForm(undefined)).toEqual(EMPTY)
    })
})

describe('unusedBuckets', () => {
    it('leaves out the buckets an item is named after', () => {
        const used = item('a')
        used.record.properties.name = 'Cycle time of system'

        const names = unusedBuckets([used, item('b')]).map((bucket) => bucket.name)

        expect(names).toHaveLength(BUCKETS.length - 1)
        expect(names).not.toContain('Cycle time of system')
    })
})

describe('knowledgeDetails', () => {
    it('lists only the filled details, in ontology order', () => {
        const entry = item('a')
        entry.record.properties.recommendation = 'Chamfer it'
        entry.record.properties.reasoning = 'Parts jam'

        expect(knowledgeDetails(entry)).toEqual([
            { key: 'reasoning', label: 'Reasoning', value: 'Parts jam' },
            { key: 'recommendation', label: 'Recommendation', value: 'Chamfer it' },
        ])
    })
})
