import { z } from 'zod'

export const MACHINES_PER_PAGE = 10

// Invalid values are dropped instead of failing the route: the page then falls back to its defaults
export const machinesSearchSchema = z.object({
    page: z.number().int().min(1).optional().catch(undefined),
    machine: z.string().optional().catch(undefined),
})

export type MachinesSearch = z.output<typeof machinesSearchSchema>
