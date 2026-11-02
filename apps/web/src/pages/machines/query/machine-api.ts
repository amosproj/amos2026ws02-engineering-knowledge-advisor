import { z } from 'zod'

import { queryMaker } from '@queries/query-maker'

const machineParams = z.object({ id: z.string() })

const machineSchema = z.object({
    id: z.string(),
    status: z.enum(['uploading', 'processing', 'ready', 'failed']),
    error_code: z.string().nullable(),
})

export type MachineState = z.output<typeof machineSchema>

export const createMachine = queryMaker({
    method: 'POST',
    path: '/v1/machines',
    body: z.object({
        name: z.string(),
        description: z.string().optional(),
        filename: z.string(),
        size: z.number(),
    }),
    response: z.object({
        id: z.string(),
        upload: z.object({ url: z.string(), fields: z.record(z.string(), z.string()) }),
    }),
})

export const completeMachineUpload = queryMaker({
    method: 'POST',
    path: '/v1/machines/:id/complete',
    params: machineParams,
    response: machineSchema,
})

export const getMachine = queryMaker({
    method: 'GET',
    path: '/v1/machines/:id',
    params: machineParams,
    response: machineSchema,
})

export const deleteMachine = queryMaker({
    method: 'DELETE',
    path: '/v1/machines/:id',
    params: machineParams,
    response: z.void(),
})
