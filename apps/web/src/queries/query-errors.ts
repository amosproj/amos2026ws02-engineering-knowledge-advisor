import { z } from 'zod'

/** Base of every error thrown by the query layer,
 * narrow on _tag
 * */
export abstract class QueryError extends Error {
    abstract readonly _tag: string
}

const httpTags = {
    400: 'BadRequest',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'NotFound',
    409: 'Conflict',
    429: 'TooManyRequests',
} as const

export type HttpTag = (typeof httpTags)[keyof typeof httpTags] | 'ServerError' | 'UnexpectedStatus'

// Non-2xx response without a declared custom error.
export class HttpError<Tag extends HttpTag = HttpTag> extends QueryError {
    readonly _tag: Tag
    readonly status: number
    readonly data: unknown
    // _tag sent by the backend that no error definition matched.
    readonly backendTag: string | undefined

    constructor(tag: Tag, status: number, message: string, data: unknown, backendTag?: string) {
        super(message)
        this.name = 'HttpError'
        this._tag = tag
        this.status = status
        this.data = data
        this.backendTag = backendTag
    }
}

const validationIssueSchema = z.object({
    type: z.string(),
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
})

export type ValidationIssue = z.output<typeof validationIssueSchema>

// FastAPI request validation failure (422 with a list of issues).
export class ValidationError extends QueryError {
    readonly _tag = 'Validation'
    readonly status = 422
    readonly issues: ValidationIssue[]

    constructor(issues: ValidationIssue[]) {
        super(issues.map((issue) => `${issue.loc.slice(1).join('.')}: ${issue.msg}`).join('; '))
        this.name = 'ValidationError'
        this.issues = issues
    }
}

//The server could not be reached (offline, DNS, CORS…)
export class NetworkError extends QueryError {
    readonly _tag = 'Network'

    constructor(cause: unknown) {
        super('Unable to reach the server', { cause })
        this.name = 'NetworkError'
    }
}

// 2xx response that is not valid JSON or does not match the response schema.
export class DecodeError extends QueryError {
    readonly _tag = 'Decode'

    constructor(cause: unknown) {
        super('Unexpected response from the server', { cause })
        this.name = 'DecodeError'
    }
}

// The request input failed validation, nothing was sent.
export class InvalidInputError extends QueryError {
    readonly _tag = 'InvalidInput'

    constructor(message: string, cause?: unknown) {
        super(message, { cause })
        this.name = 'InvalidInputError'
    }
}

// Every tag thrown by any endpoint, as a discriminated union.
export type StandardError =
    | { [Tag in HttpTag]: HttpError<Tag> }[HttpTag]
    | ValidationError
    | NetworkError
    | DecodeError
    | InvalidInputError

export interface ErrorDefinition<E extends QueryError = QueryError> {
    readonly tag: string
    readonly schema: z.ZodType
    new (status: number, message: string, data: never): E
}

/**
 * Define a custom error matched on the `_tag` the backend puts in `detail`.
 * `message` becomes the error message, `schema` validates the other fields of `detail`.
 * If the tag is not declared or the schema fails, it falls back to a standard `HttpError`.
 *
 * @example Backend (FastAPI)
 * ```python
 * raise HTTPException(
 *     status_code=400,
 *     detail={"_tag": "TooManyTodos", "message": "Cannot create more than 2 todos", "max": 2},
 * )
 * ```
 *
 * @example Frontend
 * ```ts
 * export class TooManyTodos extends defineError('TooManyTodos', z.object({ max: z.number() })) {}
 *
 * const createTodo = queryMaker({ method: 'POST', path: '/todos', response: todoSchema, errors: [TooManyTodos] })
 *
 * if (mutation.error?._tag === 'TooManyTodos') mutation.error.data.max // correctly typed as number
 * ```
 */
export function defineError<const Tag extends string, S extends z.ZodType>(tag: Tag, schema: S) {
    return class extends QueryError {
        static readonly tag = tag
        static readonly schema = schema
        readonly _tag: Tag = tag
        readonly status: number
        readonly data: z.output<S>

        constructor(status: number, message: string, data: z.output<S>) {
            super(message)
            this.name = tag
            this.status = status
            this.data = data
        }
    }
}

const taggedDetailSchema = z.looseObject({ _tag: z.string(), message: z.string().optional() })

function httpError(status: number, message: string, data: unknown, backendTag?: string) {
    const tag: HttpTag =
        status >= 500
            ? 'ServerError'
            : (httpTags[status as keyof typeof httpTags] ?? 'UnexpectedStatus')
    return new HttpError(tag, status, message, data, backendTag)
}

/**
 * Map a non-2xx response to an error, from most to least specific:
 * declared tagged error -> undeclared tag → `{ detail: string }` → 422 issues → status only.
 */
export function toResponseError(
    status: number,
    data: unknown,
    definitions: readonly ErrorDefinition[],
): QueryError {
    const detail =
        typeof data === 'object' && data !== null && 'detail' in data ? data.detail : undefined

    const tagged = taggedDetailSchema.safeParse(detail)
    if (tagged.success) {
        const { _tag, message = _tag } = tagged.data
        const Definition = definitions.find((definition) => definition.tag === _tag)
        if (Definition) {
            const parsed = Definition.schema.safeParse(detail)
            if (parsed.success) return new Definition(status, message, parsed.data as never)
            console.warn(`Error "${_tag}" does not match its schema`, parsed.error)
        }
        return httpError(status, message, data, _tag)
    }

    if (typeof detail === 'string') return httpError(status, detail, data)

    if (status === 422) {
        const issues = z.array(validationIssueSchema).safeParse(detail)
        if (issues.success) return new ValidationError(issues.data)
    }

    return httpError(status, `Request failed (HTTP ${status})`, data)
}

type Tagged = { readonly _tag: string }

type TagHandlers<E extends Tagged, R> = {
    [Tag in E['_tag']]: (error: Extract<E, { _tag: Tag }>) => R
}

/**
 * Helper to map an error to a value by `_tag`, like a `switch`.
 * Each handler receives the error narrowed to its tag. `orElse` handles the remaining tags
 * and is required unless every tag of the error is handled.
 *
 * @example Partial, with a fallback
 * ```ts
 * matchError(createTodo.error, {
 *     TooManyTodos: (error) => `Limit of ${error.data.max} todos reached`,
 *     Network: () => 'Server unreachable',
 *     orElse: (error) => error.message,
 * })
 * ```
 *
 * @example Exhaustive: compilation fails if a tag is missing
 * ```ts
 * matchError(error, { NotFound: () => 404, Validation: () => 422, … })
 * ```
 */
export function matchError<E extends Tagged, R>(error: E, handlers: TagHandlers<E, R>): R
export function matchError<E extends Tagged, R>(
    error: E,
    handlers: Partial<TagHandlers<E, R>> & { orElse: (error: E) => R },
): R
export function matchError(
    error: Tagged,
    handlers: Record<string, ((error: Tagged) => unknown) | undefined>,
) {
    const handler = handlers[error._tag] ?? handlers.orElse
    return handler?.(error)
}
