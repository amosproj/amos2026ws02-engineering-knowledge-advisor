import { z } from 'zod'

export const STEP_FILE_ACCEPT = ['.stp', '.step']
export const STEP_FILE_MAX_SIZE = 5 * 1024 * 1024 * 1024 // 5 GB

const name = (label: string) =>
    z
        .string()
        .trim()
        .min(1, `Enter the ${label}.`)
        .max(255, `The ${label} must be 255 characters or fewer.`)

const optionalText = (label: string, max: number) =>
    z.string().trim().max(max, `The ${label} must be ${max} characters or fewer.`)

export const machineFormSchema = z.object({
    name: name('machine name'),
    identifier: optionalText('identifier', 255),
    customer: optionalText('customer', 255),
    description: optionalText('description', 1000),
})

export type MachineForm = z.output<typeof machineFormSchema>

/** Blank optional text is sent as null, which clears the field. */
export function orNull(value: string) {
    return value || null
}
