import { queryOptions } from '@tanstack/react-query'
import { z } from 'zod'

import { queryMaker } from '@queries/query-maker'

const machineParams = z.object({ id: z.string() })

const machineSchema = z.object({
    id: z.string(),
    name: z.string(),
    description: z.string().nullable(),
    status: z.enum(['uploading', 'processing', 'ready', 'failed']),
    error_code: z.string().nullable(),
    original_filename: z.string(),
    size_bytes: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
})

const machineStateSchema = machineSchema.pick({ id: true, status: true, error_code: true })

export type Machine = z.output<typeof machineSchema>
export type MachineStatus = Machine['status']
export type MachineState = z.output<typeof machineStateSchema>

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
    response: machineStateSchema,
})

export const listMachines = queryMaker({
    method: 'GET',
    path: '/v1/machines',
    response: z.array(machineSchema),
})

export const getMachine = queryMaker({
    method: 'GET',
    path: '/v1/machines/:id',
    params: machineParams,
    response: machineStateSchema,
})

export const updateMachine = queryMaker({
    method: 'PATCH',
    path: '/v1/machines/:id',
    params: machineParams,
    body: z.object({ name: z.string(), description: z.string() }),
    response: machineSchema,
})

export const deleteMachine = queryMaker({
    method: 'DELETE',
    path: '/v1/machines/:id',
    params: machineParams,
    response: z.void(),
})

export const machinesQueryKey = ['machines'] as const

export const machinesQuery = queryOptions({
    queryKey: machinesQueryKey,
    queryFn: ({ signal }) => listMachines({ signal }),
})
