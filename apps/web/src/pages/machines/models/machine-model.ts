import { z } from 'zod'

import type { MachineView } from '../query/machine-api'

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

// The file picker already rejects other extensions, empty files and files over the size limit
const stepFile = z
    .instanceof(File)
    .nullable()
    .refine(
        (file) => !file || file.name.length <= 255,
        'The file name must be 255 characters or fewer.',
    )

export const machineFormSchema = z.object({
    name: name('machine name'),
    identifier: optionalText('identifier', 255),
    customer: optionalText('customer', 255),
    description: optionalText('description', 1000),
    size: z
        .string()
        .trim()
        .refine((size) => size === '' || Number.isFinite(Number(size)), 'Enter a number.'),
    file: stepFile,
})

export type MachineForm = z.output<typeof machineFormSchema>

export const cadFileFormSchema = z.object({
    file: stepFile.refine((file) => Boolean(file), 'Select a STEP file.'),
})

export type CadFileForm = z.output<typeof cadFileFormSchema>

/** Blank optional text is sent as null, which clears the field. */
export function orNull(value: string) {
    return value || null
}

export function toSize(size: string) {
    return size === '' ? null : Number(size)
}

export function findCadFile(machine: MachineView) {
    return machine.children.find((child) => child['@type'] === 'CadFile')
}
