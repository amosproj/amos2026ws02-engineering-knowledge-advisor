import { describe, expect, expectTypeOf, it, vi } from 'vitest'
import { z } from 'zod'
import {
    defineProblem,
    HttpError,
    matchError,
    NetworkError,
    toResponseError,
    ValidationError,
    type StandardError,
    type ValidationIssue,
} from './query-errors'

class TooManyTodos extends defineProblem(
    'urn:eka:problem:too-many-todos',
    z.object({ max: z.number() }),
) {}

// Bodies as sent by the FastAPI exception handlers.
const tooManyTodos = {
    type: 'urn:eka:problem:too-many-todos',
    title: 'Too many todos',
    status: 409,
    detail: 'Cannot create more than 2 todos',
    instance: '/api/v1/todos',
    max: 2,
}

const notFound = {
    type: 'about:blank',
    title: 'Not Found',
    status: 404,
    detail: 'Todo not found',
    instance: '/api/v1/todos/12',
}

const validationFailed = {
    type: 'about:blank',
    title: 'Unprocessable Content',
    status: 422,
    detail: 'Request validation failed',
    instance: '/api/v1/ping',
    errors: [
        {
            type: 'int_parsing',
            loc: ['body', 'ping'],
            msg: 'Input should be a valid integer',
            input: 'nan',
        },
    ],
}

describe('toResponseError', () => {
    it('maps a declared problem type to its custom error', () => {
        const error = toResponseError(409, tooManyTodos, [TooManyTodos])

        expect(error).toBeInstanceOf(TooManyTodos)
        expect(error._tag).toBe('urn:eka:problem:too-many-todos')
        expect(error.message).toBe('Cannot create more than 2 todos')
        expect((error as TooManyTodos).data).toEqual({ max: 2 })
        expect((error as TooManyTodos).problem.instance).toBe('/api/v1/todos')
    })

    it('falls back to a status error when the problem type is not declared', () => {
        const error = toResponseError(409, tooManyTodos, [])

        expect(error).toBeInstanceOf(HttpError)
        expect(error._tag).toBe('Conflict')
        expect(error.message).toBe('Cannot create more than 2 todos')
    })

    it('falls back to a status error and warns when the extensions do not match', () => {
        const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

        const error = toResponseError(409, { ...tooManyTodos, max: 'two' }, [TooManyTodos])

        expect(error._tag).toBe('Conflict')
        expect(warn).toHaveBeenCalledOnce()
        warn.mockRestore()
    })

    it.each([
        [400, 'BadRequest'],
        [401, 'Unauthorized'],
        [403, 'Forbidden'],
        [404, 'NotFound'],
        [409, 'Conflict'],
        [429, 'TooManyRequests'],
        [500, 'ServerError'],
        [503, 'ServerError'],
        [418, 'UnexpectedStatus'],
    ])('maps an about:blank %i to %s', (status, tag) => {
        const error = toResponseError(status, { ...notFound, status }, [])

        expect(error).toBeInstanceOf(HttpError)
        expect(error._tag).toBe(tag)
        expect((error as HttpError).status).toBe(status)
    })

    it('uses detail, then title, then the status as message', () => {
        expect(toResponseError(404, notFound, []).message).toBe('Todo not found')
        expect(toResponseError(404, { ...notFound, detail: undefined }, []).message).toBe(
            'Not Found',
        )
        expect(toResponseError(404, { type: 'about:blank' }, []).message).toBe(
            'Request failed (HTTP 404)',
        )
    })

    it('keeps the raw problem on status errors', () => {
        const error = toResponseError(404, notFound, []) as HttpError

        expect(error.problem?.instance).toBe('/api/v1/todos/12')
    })

    it('maps a 422 with validation issues to a ValidationError', () => {
        const error = toResponseError(422, validationFailed, [])

        expect(error).toBeInstanceOf(ValidationError)
        expect(error._tag).toBe('Validation')
        expect((error as ValidationError).issues).toHaveLength(1)
        expect(error.message).toBe('ping: Input should be a valid integer')
    })

    it('maps a 422 without validation issues to a status error', () => {
        const error = toResponseError(422, { ...validationFailed, errors: undefined }, [])

        expect(error).toBeInstanceOf(HttpError)
        expect(error._tag).toBe('UnexpectedStatus')
    })

    it('handles a body that is not a problem', () => {
        const error = toResponseError(502, '<html>Bad Gateway</html>', []) as HttpError

        expect(error._tag).toBe('ServerError')
        expect(error.message).toBe('Request failed (HTTP 502)')
        expect(error.problem).toBeUndefined()
    })

    it('treats a missing type as about:blank', () => {
        const error = toResponseError(404, { detail: 'Todo not found' }, [TooManyTodos])

        expect(error._tag).toBe('NotFound')
        expect((error as HttpError).problem?.type).toBe('about:blank')
    })
})

describe('matchError', () => {
    type Err = StandardError | TooManyTodos

    const describeError = (error: Err) =>
        matchError(error, {
            'urn:eka:problem:too-many-todos': (e) => `max ${e.data.max}`,
            Network: () => 'offline',
            orElse: (e) => e.message,
        })

    it('calls the handler of the error tag', () => {
        expect(describeError(toResponseError(409, tooManyTodos, [TooManyTodos]) as Err)).toBe(
            'max 2',
        )
        expect(describeError(new NetworkError(new TypeError('Failed to fetch')))).toBe('offline')
    })

    it('calls orElse for unhandled tags', () => {
        expect(describeError(toResponseError(404, notFound, []) as Err)).toBe('Todo not found')
    })
})

describe('types', () => {
    type Err = StandardError | TooManyTodos

    it('narrows on the problem type', () => {
        const error = {} as Err

        if (error._tag === 'urn:eka:problem:too-many-todos') {
            expectTypeOf(error.data).toEqualTypeOf<{ max: number }>()
        }
        if (error._tag === 'Validation') {
            expectTypeOf(error.issues).toEqualTypeOf<ValidationIssue[]>()
        }

        // @ts-expect-error data only exists after narrowing
        void error.data
        // @ts-expect-error unknown tag
        void (error._tag === 'Typo')
    })

    it('requires every tag when orElse is missing', () => {
        const error = {} as NetworkError | TooManyTodos

        matchError(error, {
            Network: () => 1,
            'urn:eka:problem:too-many-todos': () => 2,
        })

        // @ts-expect-error missing handler for 'urn:eka:problem:too-many-todos'
        matchError(error, { Network: () => 1 })
    })
})
