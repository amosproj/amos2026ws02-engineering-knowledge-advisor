import { z } from 'zod'

/** Base of every error thrown by the query layer, narrow on `_tag`. */
export abstract class QueryError extends Error {
    abstract readonly _tag: string
}

// RFC 9457 problem details, extension members are kept as-is.
const problemSchema = z.looseObject({
    type: z.string().catch('about:blank'),
    title: z.string().nullish(),
    status: z.number().nullish(),
    detail: z.string().nullish(),
    instance: z.string().nullish(),
})

export type Problem = z.output<typeof problemSchema>

const httpTags = {
    400: 'BadRequest',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'NotFound',
    409: 'Conflict',
    429: 'TooManyRequests',
} as const

export type HttpTag = (typeof httpTags)[keyof typeof httpTags] | 'ServerError' | 'UnexpectedStatus'

// Non-2xx response without a declared problem type.
export class HttpError<Tag extends HttpTag = HttpTag> extends QueryError {
    readonly _tag: Tag
    readonly status: number
    // Undefined when the body is not a problem (e.g. a proxy error page).
    readonly problem: Problem | undefined

    constructor(tag: Tag, status: number, message: string, problem?: Problem) {
        super(message)
        this.name = 'HttpError'
        this._tag = tag
        this.status = status
        this.problem = problem
    }
}

const validationIssueSchema = z.looseObject({
    type: z.string(),
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
})

export type ValidationIssue = z.output<typeof validationIssueSchema>

// FastAPI request validation failure (422, issues in the `errors` extension).
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

// The server could not be reached (offline, DNS, CORS…).
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

export interface ProblemDefinition<E extends QueryError = QueryError> {
    readonly type: string
    readonly schema: z.ZodType
    new (status: number, message: string, data: never, problem: Problem): E
}

/**
 * Define a custom error matched on the RFC 9457 `type` sent by the backend.
 * The `type` string becomes the `_tag`, `schema` validates the extension members.
 * If the schema fails, it falls back to a standard `HttpError`.
 *
 * @example Backend (FastAPI)
 * ```python
 * raise ProblemException(Problem(
 *     type="urn:eka:problem:too-many-todos",
 *     title="Too many todos",
 *     status=409,
 *     detail="Cannot create more than 2 todos",
 *     max=2,
 * ))
 * ```
 *
 * @example Frontend
 * ```ts
 * export class TooManyTodos extends defineProblem(
 *     'urn:eka:problem:too-many-todos',
 *     z.object({ max: z.number() }),
 * ) {}
 *
 * const createTodo = queryMaker({ method: 'POST', path: '/v1/todos', response: todoSchema, errors: [TooManyTodos] })
 *
 * if (mutation.error?._tag === 'urn:eka:problem:too-many-todos') mutation.error.data.max // typed as number
 * ```
 */
export function defineProblem<const Type extends string, S extends z.ZodType>(
    type: Type,
    schema: S,
) {
    return class extends QueryError {
        static readonly type = type
        static readonly schema = schema
        readonly _tag: Type = type
        readonly status: number
        readonly data: z.output<S>
        readonly problem: Problem

        constructor(status: number, message: string, data: z.output<S>, problem: Problem) {
            super(message)
            this.name = type
            this.status = status
            this.data = data
            this.problem = problem
        }
    }
}

function httpError(status: number, message: string, problem?: Problem) {
    const tag: HttpTag =
        status >= 500
            ? 'ServerError'
            : (httpTags[status as keyof typeof httpTags] ?? 'UnexpectedStatus')
    return new HttpError(tag, status, message, problem)
}

/**
 * Map a non-2xx response to an error, from most to least specific:
 * declared problem type → 422 validation issues → status only.
 */
export function toResponseError(
    status: number,
    data: unknown,
    definitions: readonly ProblemDefinition[],
): QueryError {
    const parsedProblem = problemSchema.safeParse(data)
    if (!parsedProblem.success) return httpError(status, `Request failed (HTTP ${status})`)

    const problem = parsedProblem.data
    const message = problem.detail || problem.title || `Request failed (HTTP ${status})`

    const Definition = definitions.find((definition) => definition.type === problem.type)
    if (Definition) {
        const parsed = Definition.schema.safeParse(problem)
        if (parsed.success) return new Definition(status, message, parsed.data as never, problem)
        console.warn(`Problem "${problem.type}" does not match its schema`, parsed.error)
    }

    if (status === 422) {
        const issues = z.array(validationIssueSchema).safeParse(problem.errors)
        if (issues.success) return new ValidationError(issues.data)
    }

    return httpError(status, message, problem)
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
 *     'urn:eka:problem:too-many-todos': (error) => `Limit of ${error.data.max} todos reached`,
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
