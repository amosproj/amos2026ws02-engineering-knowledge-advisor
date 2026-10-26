import { env } from '@utils/env'
import { z } from 'zod'
import {
    DecodeError,
    InvalidInputError,
    NetworkError,
    toResponseError,
    type ProblemDefinition,
    type StandardError,
} from './query-errors'

const apiBaseUrl = env.VITE_API_URL

type PathParams = Record<string, string | number>
type SearchValue = string | number | boolean | null | undefined
type SearchParams = Record<string, SearchValue | readonly SearchValue[]>
type Schema = z.ZodType | undefined
type InputField<Key extends string, S extends Schema> = S extends z.ZodType
    ? { [K in Key]: z.input<S> }
    : { [K in Key]?: never }

declare const errorType: unique symbol

/** Validated HTTP function. `[errorType]` only carries the error union for typing. */
export type Endpoint<Input, Output, Err> = ((input: Input) => Promise<Output>) & {
    readonly [errorType]: Err
}

export type InputOf<E> = E extends Endpoint<infer Input, unknown, unknown> ? Input : never
export type ErrorOf<E> = E extends Endpoint<never, unknown, infer Err> ? Err : never

async function parseInput<S extends z.ZodType>(schema: S, value: unknown, label: string) {
    const parsed = await schema.safeParseAsync(value)
    if (!parsed.success) throw new InvalidInputError(`Invalid ${label}`, parsed.error)
    return parsed.data
}

/** Build a validated HTTP function, query/mutation options stay in domain files. */
export function queryMaker<
    ResponseSchema extends z.ZodType,
    BodySchema extends Schema = undefined,
    ParamsSchema extends z.ZodType<PathParams> | undefined = undefined,
    SearchSchema extends z.ZodType<SearchParams> | undefined = undefined,
    Errors extends readonly ProblemDefinition[] = [],
>(options: {
    method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
    path: string
    response: ResponseSchema
    body?: BodySchema
    params?: ParamsSchema
    search?: SearchSchema
    // Custom errors, matched on the RFC 9457 problem `type`.
    errors?: Errors
}) {
    type Input = InputField<'body', BodySchema> &
        InputField<'params', ParamsSchema> &
        InputField<'search', SearchSchema> & { signal?: AbortSignal }

    type Err = StandardError | InstanceType<Errors[number]>

    const request = async (input: Input): Promise<z.output<ResponseSchema>> => {
        // Parse first: invalid inputs must never reach the network.
        const body = options.body ? await parseInput(options.body, input.body, 'body') : undefined
        const params: PathParams = options.params
            ? await parseInput(options.params, input.params, 'path parameters')
            : {}
        const search: SearchParams = options.search
            ? await parseInput(options.search, input.search, 'search parameters')
            : {}

        const path = options.path.replace(/:([A-Za-z0-9_]+)/g, (_match, key: string) => {
            const value = params[key]
            if (value === undefined) throw new InvalidInputError(`Missing path parameter: ${key}`)
            return encodeURIComponent(String(value))
        })
        const url = new URL(
            `${apiBaseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`,
            window.location.origin,
        )

        for (const [key, value] of Object.entries(search)) {
            for (const item of Array.isArray(value) ? value : [value]) {
                if (item !== undefined && item !== null) url.searchParams.append(key, String(item))
            }
        }

        let response: Response
        try {
            response = await fetch(url, {
                method: options.method,
                signal: input.signal,
                headers: {
                    Accept: 'application/json, application/problem+json',
                    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
                },
                ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
            })
        } catch (error) {
            // Cancellation is not a failure: React Query handle the abort.
            if (input.signal?.aborted) throw error
            throw new NetworkError(error)
        }

        const text = await response.text()
        let data: unknown
        if (text) {
            try {
                data = JSON.parse(text)
            } catch (error) {
                if (response.ok) throw new DecodeError(error)
                data = text
            }
        }

        if (!response.ok) throw toResponseError(response.status, data, options.errors ?? [])

        // Empty responses (including 204) are validated as undefined with z.void().
        const parsed = await options.response.safeParseAsync(data)
        if (!parsed.success) throw new DecodeError(parsed.error)
        return parsed.data
    }

    return request as Endpoint<Input, z.output<ResponseSchema>, Err>
}
