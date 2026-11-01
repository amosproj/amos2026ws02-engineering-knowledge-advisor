import { z } from 'zod'

export const STEP_FILE_ACCEPT = ['.stp', '.step']
export const STEP_FILE_MAX_SIZE = 1024 * 1024 * 1024 // 1 GB

export const importMachineSchema = z.object({
    machineName: z
        .string()
        .trim()
        .min(1, 'Enter the machine name.')
        .max(255, 'The machine name must be 255 characters or fewer.'),
    file: z.instanceof(File, { error: 'Select a STEP file.' }),
})

export type MachineImport = z.output<typeof importMachineSchema>

export type ImportMachineValues = {
    machineName: string
    file: File | null
}
