import { env } from '@utils/env'
import { z } from 'zod'

const apiBaseUrl = env.VITE_API_URL

type PathParams = Record<string, string | number>
type SearchValue = string | number | boolean | null | undefined
type SearchParams = Record<string, SearchValue | readonly SearchValue[]>
type Schema = z.ZodType | undefined
type InputField<Key extends string, S extends Schema> = S extends z.ZodType
    ? { [K in Key]: z.input<S> }
    : { [K in Key]?: never }

export class HttpError extends Error {
    readonly status: number
    readonly data: unknown

    constructor(response: Response, data: unknown) {
        super(`HTTP ${response.status}: ${response.statusText || 'Request failed'}`)
        this.name = 'HttpError'
        this.status = response.status
        this.data = data
    }
}

/** Build a validated HTTP function; query/mutation options stay in domain files. */
export function queryMaker<
    ResponseSchema extends z.ZodType,
    BodySchema extends Schema = undefined,
    ParamsSchema extends z.ZodType<PathParams> | undefined = undefined,
    SearchSchema extends z.ZodType<SearchParams> | undefined = undefined,
>(options: {
    method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
    path: string
    response: ResponseSchema
    body?: BodySchema
    params?: ParamsSchema
    search?: SearchSchema
}) {
    type Input = InputField<'body', BodySchema> &
        InputField<'params', ParamsSchema> &
        InputField<'search', SearchSchema> & { signal?: AbortSignal }

    return async (input: Input): Promise<z.output<ResponseSchema>> => {
        // Parse first: invalid inputs must never reach the network.
        const body = options.body ? await options.body.parseAsync(input.body) : undefined
        const params = options.params ? await options.params.parseAsync(input.params) : {}
        const search = options.search ? await options.search.parseAsync(input.search) : {}

        const path = options.path.replace(/:([A-Za-z0-9_]+)/g, (_match, key: string) => {
            const value = params[key]
            if (value === undefined) throw new TypeError(`Missing path parameter: ${key}`)
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

        const response = await fetch(url, {
            method: options.method,
            signal: input.signal,
            headers: {
                Accept: 'application/json',
                ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
            },
            ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        })

        const text = await response.text()
        let data: unknown
        if (text) {
            try {
                data = JSON.parse(text)
            } catch {
                if (response.ok) throw new SyntaxError('The API response is not valid JSON')
                data = text
            }
        }

        if (!response.ok) throw new HttpError(response, data)

        // Empty responses (including 204) are validated as undefined with z.void().
        return options.response.parseAsync(data)
    }
}
