import { queryOptions } from '@tanstack/react-query'
import { z } from 'zod'

import { NetworkError, toResponseError } from '@queries/query-errors'
import { queryMaker } from '@queries/query-maker'
import { env } from '@utils/env'

const idParams = z.object({ id: z.string() })
const includeSearch = z.object({ include: z.string() })

const uploadStatus = z.enum(['uploading', 'processing', 'ready', 'failed'])
const fileStatus = z.enum(['empty', ...uploadStatus.options])

const machineSchema = z.looseObject({
    '@id': z.string(),
    name: z.string(),
    identifier: z.string().optional(),
    customer: z.string().optional(),
    description: z.string().optional(),
})

const childSchema = z.looseObject({
    '@id': z.string(),
    '@type': z.string(),
    name: z.string().optional(),
})

const machineViewSchema = z.object({
    record: machineSchema,
    version: z.string(),
    status: fileStatus,
    children: z.array(childSchema),
})

const instanceSchema = z.looseObject({
    '@id': z.string(),
    '@type': z.string(),
    name: z.string().optional(),
    instanceOf: z.string().optional(),
})

type RecordTree = { record: z.output<typeof instanceSchema>; children: RecordTree[] }

const recordTreeSchema: z.ZodType<RecordTree> = z.object({
    record: instanceSchema,
    get children() {
        return z.array(recordTreeSchema)
    },
})

const groupSchema = z.looseObject({
    '@id': z.string(),
    name: z.string(),
    identifier: z.string().optional(),
    description: z.string().optional(),
    properties: z
        .looseObject({
            sizeX: z.number().optional(),
            sizeY: z.number().optional(),
            sizeZ: z.number().optional(),
        })
        .optional(),
})

const uploadSchema = z.object({
    id: z.string(),
    status: uploadStatus,
    errorCode: z.string().nullable(),
    sizeBytes: z.number(),
    createdAt: z.string(),
    updatedAt: z.string(),
})

const cadFileViewSchema = z.object({
    record: z.looseObject({ '@id': z.string(), name: z.string() }),
    version: z.string(),
    status: fileStatus,
    upload: uploadSchema.nullable(),
})

const writtenSchema = z.object({
    id: z.string(),
    warnings: z.array(z.string()),
    version: z.string(),
})

const machineBody = z.object({
    '@type': z.literal('Machine'),
    name: z.string(),
    identifier: z.string().optional(),
    customer: z.string().optional(),
    description: z.string().optional(),
})

// JSON Merge Patch: null removes a property
const machineChanges = z.object({
    name: z.string(),
    identifier: z.string().nullable(),
    customer: z.string().nullable(),
    description: z.string().nullable(),
})

const cadFileBody = z.object({
    '@type': z.literal('CadFile'),
    name: z.string(),
    format: z.string(),
    timestamp: z.string(),
    partOf: z.string(),
})

const cadFileChanges = cadFileBody.pick({ name: true, timestamp: true })

export type Machine = z.output<typeof machineSchema>
export type MachineView = z.output<typeof machineViewSchema>
export type FileStatus = z.output<typeof fileStatus>
export type CadFileView = z.output<typeof cadFileViewSchema>
export type AssemblyGroup = z.output<typeof groupSchema>
export type { RecordTree }

export const listMachines = queryMaker({
    method: 'GET',
    path: '/v1/records',
    search: includeSearch.extend({ cls: z.literal('Machine') }),
    response: z.array(machineViewSchema),
})

export const createMachine = queryMaker({
    method: 'POST',
    path: '/v1/records',
    body: machineBody,
    response: writtenSchema,
})

export const updateMachine = queryMaker({
    method: 'PATCH',
    path: '/v1/records/:id',
    params: idParams,
    body: machineChanges,
    response: writtenSchema,
})

export const deleteRecord = queryMaker({
    method: 'DELETE',
    path: '/v1/records/:id',
    params: idParams,
    response: z.object({ deletedIds: z.array(z.string()), markedIds: z.array(z.string()) }),
})

export const createCadFile = queryMaker({
    method: 'POST',
    path: '/v1/records',
    body: cadFileBody,
    response: writtenSchema,
})

export const updateCadFile = queryMaker({
    method: 'PATCH',
    path: '/v1/records/:id',
    params: idParams,
    body: cadFileChanges,
    response: writtenSchema,
})

export const getCadFile = queryMaker({
    method: 'GET',
    path: '/v1/records/:id',
    params: idParams,
    search: includeSearch,
    response: cadFileViewSchema,
})

export const getMachine = queryMaker({
    method: 'GET',
    path: '/v1/records/:id',
    params: idParams,
    search: includeSearch,
    response: machineViewSchema,
})

export const listChildInstances = queryMaker({
    method: 'GET',
    path: '/v1/records',
    search: z.object({ cls: z.literal('AssemblyInstance'), parentId: z.string() }),
    response: z.array(instanceSchema),
})

export const getRecordTree = queryMaker({
    method: 'GET',
    path: '/v1/records/:id/tree',
    params: idParams,
    response: recordTreeSchema,
})

export const getAssemblyGroup = queryMaker({
    method: 'GET',
    path: '/v1/records/:id',
    params: idParams,
    response: groupSchema,
})

export const requestUploadForm = queryMaker({
    method: 'POST',
    path: '/v1/records/:id/upload-form',
    params: idParams,
    body: z.object({ size: z.number() }),
    response: z.object({ url: z.string(), fields: z.record(z.string(), z.string()) }),
})

export const completeUpload = queryMaker({
    method: 'POST',
    path: '/v1/records/:id/complete',
    params: idParams,
    response: uploadSchema,
})

// Prefix of every machine query
export const machinesQueryKey = ['machines'] as const

export const machinesQuery = queryOptions({
    queryKey: machinesQueryKey,
    queryFn: ({ signal }) =>
        listMachines({ search: { cls: 'Machine', include: 'status,children' }, signal }),
})

export const cadFileQuery = (id: string) =>
    queryOptions({
        queryKey: [...machinesQueryKey, 'cad-files', id],
        queryFn: ({ signal }) =>
            getCadFile({ params: { id }, search: { include: 'status,upload' }, signal }),
    })

export const machineQuery = (id: string) =>
    queryOptions({
        queryKey: [...machinesQueryKey, id],
        queryFn: ({ signal }) =>
            getMachine({ params: { id }, search: { include: 'status,children' }, signal }),
    })

// null when the machine has no assembly tree
export const assemblyTreeQuery = (machineId: string) =>
    queryOptions({
        queryKey: [...machinesQueryKey, machineId, 'tree'],
        queryFn: async ({ signal }) => {
            const [root] = await listChildInstances({
                search: { cls: 'AssemblyInstance', parentId: machineId },
                signal,
            })
            return root ? getRecordTree({ params: { id: root['@id'] }, signal }) : null
        },
    })

export const assemblyGroupQuery = (id: string) =>
    queryOptions({
        queryKey: [...machinesQueryKey, 'groups', id],
        queryFn: ({ signal }) => getAssemblyGroup({ params: { id }, signal }),
    })

// Bytes of the CAD file's 3D model (GLB), following the redirect to the storage
export async function fetchModel(fileId: string, signal?: AbortSignal) {
    const url = `${env.VITE_API_URL.replace(/\/$/, '')}/v1/records/${encodeURIComponent(fileId)}/model`
    try {
        const response = await fetch(url, { signal })
        if (response.ok) return await response.arrayBuffer()
        const text = await response.text()
        let data: unknown = text
        try {
            data = JSON.parse(text)
        } catch {
            // the storage answers errors in XML
        }
        throw toResponseError(response.status, data, [])
    } catch (error) {
        if (signal?.aborted || !(error instanceof TypeError)) throw error
        throw new NetworkError(error)
    }
}
