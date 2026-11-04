import { queryOptions } from '@tanstack/react-query'
import { z } from 'zod'

import { queryMaker } from '@queries/query-maker'

const idParams = z.object({ id: z.string() })

const cadFileSchema = z.object({
    id: z.string(),
    name: z.string(),
    assembly_group_id: z.string(),
    status: z.enum(['uploading', 'processing', 'ready', 'failed']),
    error_code: z.string().nullable(),
    size_bytes: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
})

const assemblyGroupSchema = z.object({
    id: z.string(),
    machine_id: z.string(),
    name: z.string(),
    identifier: z.string().nullable(),
    description: z.string().nullable(),
    cad_files: z.array(cadFileSchema),
})

const machineSchema = z.object({
    id: z.string(),
    name: z.string(),
    identifier: z.string().nullable(),
    customer: z.string().nullable(),
    description: z.string().nullable(),
    assembly_group_count: z.number(),
    cad_file_count: z.number(),
    status: z.enum(['empty', 'uploading', 'processing', 'failed', 'ready']),
})

const machineDetailsSchema = machineSchema.extend({
    assembly_groups: z.array(assemblyGroupSchema),
})

// null clears an optional field
const machineBody = z.object({
    name: z.string(),
    identifier: z.string().nullable(),
    customer: z.string().nullable(),
    description: z.string().nullable(),
})

const assemblyGroupBody = machineBody.omit({ customer: true })

const uploadSchema = z.object({
    id: z.string(),
    name: z.string(),
    upload: z.object({ url: z.string(), fields: z.record(z.string(), z.string()) }),
})

export type CadFile = z.output<typeof cadFileSchema>
export type CadFileStatus = CadFile['status']
export type AssemblyGroup = z.output<typeof assemblyGroupSchema>
export type Machine = z.output<typeof machineSchema>
export type MachineStatus = Machine['status']
export type MachineDetails = z.output<typeof machineDetailsSchema>
export type RegisteredCadFile = z.output<typeof uploadSchema>

export const createMachine = queryMaker({
    method: 'POST',
    path: '/v1/machines',
    body: machineBody,
    response: machineSchema,
})

export const listMachines = queryMaker({
    method: 'GET',
    path: '/v1/machines',
    response: z.array(machineSchema),
})

export const getMachine = queryMaker({
    method: 'GET',
    path: '/v1/machines/:id',
    params: idParams,
    response: machineDetailsSchema,
})

export const updateMachine = queryMaker({
    method: 'PATCH',
    path: '/v1/machines/:id',
    params: idParams,
    body: machineBody,
    response: machineSchema,
})

export const deleteMachine = queryMaker({
    method: 'DELETE',
    path: '/v1/machines/:id',
    params: idParams,
    response: z.void(),
})

export const createAssemblyGroup = queryMaker({
    method: 'POST',
    path: '/v1/machines/:id/assembly-groups',
    params: idParams,
    body: assemblyGroupBody,
    response: assemblyGroupSchema,
})

export const updateAssemblyGroup = queryMaker({
    method: 'PATCH',
    path: '/v1/assembly-groups/:id',
    params: idParams,
    body: assemblyGroupBody,
    response: assemblyGroupSchema,
})

export const deleteAssemblyGroup = queryMaker({
    method: 'DELETE',
    path: '/v1/assembly-groups/:id',
    params: idParams,
    response: z.void(),
})

export const registerCadFiles = queryMaker({
    method: 'POST',
    path: '/v1/assembly-groups/:id/cad-files',
    params: idParams,
    body: z.object({ files: z.array(z.object({ filename: z.string(), size: z.number() })) }),
    response: z.array(uploadSchema),
})

export const completeCadFile = queryMaker({
    method: 'POST',
    path: '/v1/cad-files/:id/complete',
    params: idParams,
    response: cadFileSchema,
})

export const getCadFile = queryMaker({
    method: 'GET',
    path: '/v1/cad-files/:id',
    params: idParams,
    response: cadFileSchema,
})

export const renameCadFile = queryMaker({
    method: 'PATCH',
    path: '/v1/cad-files/:id',
    params: idParams,
    body: z.object({ name: z.string() }),
    response: cadFileSchema,
})

export const deleteCadFile = queryMaker({
    method: 'DELETE',
    path: '/v1/cad-files/:id',
    params: idParams,
    response: z.void(),
})

// Prefix of every machine query: invalidating it refreshes the list and the open machine
export const machinesQueryKey = ['machines'] as const

export const machinesQuery = queryOptions({
    queryKey: machinesQueryKey,
    queryFn: ({ signal }) => listMachines({ signal }),
})

export const machineQuery = (id: string) =>
    queryOptions({
        queryKey: [...machinesQueryKey, id],
        queryFn: ({ signal }) => getMachine({ params: { id }, signal }),
    })
