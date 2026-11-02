import { z } from 'zod'

export const STEP_FILE_ACCEPT = ['.stp', '.step']
export const STEP_FILE_MAX_SIZE = 5 * 1024 * 1024 * 1024 // 5 GB

export const importMachineSchema = z.object({
    machineName: z
        .string()
        .trim()
        .min(1, 'Enter the machine name.')
        .max(255, 'The machine name must be 255 characters or fewer.'),
    machineDescription: z
        .string()
        .trim()
        .max(1000, 'The machine description must be 1000 characters or fewer.')
        .optional(),
    file: z.instanceof(File, { error: 'Select a STEP file.' }),
})

export type MachineImport = z.output<typeof importMachineSchema>
