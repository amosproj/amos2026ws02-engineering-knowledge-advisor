import { z } from 'zod'

// VITE_* values are inlined at build time (see the web build args in compose.yaml).
// Unset build args arrive as empty strings, so treat them like missing values.
const envSchema = z.object({
    VITE_API_URL: z
        .string()
        .optional()
        .transform((value) => value || '/api'),
})

const parsed = envSchema.safeParse(import.meta.env)

if (!parsed.success) {
    throw new Error(`Invalid frontend environment:\n${z.prettifyError(parsed.error)}`)
}

export const env = parsed.data
