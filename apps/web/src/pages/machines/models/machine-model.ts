import { z } from 'zod'

export const STEP_FILE_ACCEPT = ['.stp', '.step']
export const STEP_FILE_MAX_SIZE = 5 * 1024 * 1024 * 1024 // 5 GB
export const MAX_FILES_PER_IMPORT = 5

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

export const assemblyGroupFormSchema = machineFormSchema
    .omit({ customer: true })
    .extend({ name: name('group name') })

export type AssemblyGroupForm = z.output<typeof assemblyGroupFormSchema>

export const cadFileFormSchema = z.object({ name: name('file name') })

export type CadFileForm = z.output<typeof cadFileFormSchema>

// The file picker already rejects other extensions, empty files and files over the size limit
export const importCadFilesSchema = z.object({
    files: z
        .array(z.instanceof(File))
        .min(1, 'Select at least one STEP file.')
        .max(MAX_FILES_PER_IMPORT, `Select ${MAX_FILES_PER_IMPORT} files or fewer.`)
        .refine(
            (files) => files.every((file) => file.name.length <= 255),
            'File names must be 255 characters or fewer.',
        ),
})

export type ImportCadFiles = z.output<typeof importCadFilesSchema>

/** Blank optional text is sent as null, which clears the field. */
export function orNull(value: string) {
    return value || null
}
