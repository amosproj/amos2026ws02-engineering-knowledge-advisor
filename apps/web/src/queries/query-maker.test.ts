import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { z } from 'zod'
import { DecodeError, HttpError, InvalidInputError, NetworkError } from './query-errors'
import { queryMaker } from './query-maker'

const todoSchema = z.object({ id: z.string(), title: z.string() })
const todo = { id: '1', title: 'Write tests' }

const fetchMock = vi.fn<typeof fetch>()

function respond(status: number, body?: unknown, contentType = 'application/json') {
    fetchMock.mockResolvedValueOnce(
        new Response(typeof body === 'string' ? body : JSON.stringify(body), {
            status,
            headers: { 'Content-Type': contentType },
        }),
    )
}

function lastRequest() {
    const [url, init] = fetchMock.mock.lastCall!
    return { url: new URL(String(url)), init: init! }
}

beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('window', { location: { origin: 'http://localhost' } })
})

afterEach(() => {
    fetchMock.mockReset()
    vi.unstubAllGlobals()
})

describe('queryMaker', () => {
    const getTodo = queryMaker({
        method: 'GET',
        path: '/v1/todos/:id',
        params: z.object({ id: z.string() }),
        response: todoSchema,
    })

    const createTodo = queryMaker({
        method: 'POST',
        path: '/v1/todos',
        body: z.object({ title: z.string().min(1) }),
        response: todoSchema,
    })

    it('returns the parsed response', async () => {
        respond(200, { ...todo, extra: true })

        await expect(getTodo({ params: { id: '1' } })).resolves.toEqual(todo)
    })

    it('builds the url from the api base url and encoded path params', async () => {
        respond(200, todo)

        await getTodo({ params: { id: 'a/b c' } })

        expect(lastRequest().url.href).toBe('http://localhost/api/v1/todos/a%2Fb%20c')
    })

    it('appends search params and skips empty values', async () => {
        const listTodos = queryMaker({
            method: 'GET',
            path: '/v1/todos',
            search: z.object({
                tag: z.array(z.string()),
                done: z.boolean().optional(),
                q: z.string().nullable(),
            }),
            response: z.array(todoSchema),
        })
        respond(200, [todo])

        await listTodos({ search: { tag: ['a', 'b'], q: null } })

        expect(lastRequest().url.search).toBe('?tag=a&tag=b')
    })

    it('sends the body as json with the expected headers', async () => {
        respond(201, todo)

        await createTodo({ body: { title: 'Write tests' } })

        const { init } = lastRequest()
        expect(init.method).toBe('POST')
        expect(init.body).toBe('{"title":"Write tests"}')
        expect(init.headers).toEqual({
            Accept: 'application/json, application/problem+json',
            'Content-Type': 'application/json',
        })
    })

    it('rejects an invalid input without calling the server', async () => {
        await expect(createTodo({ body: { title: '' } })).rejects.toBeInstanceOf(InvalidInputError)
        expect(fetchMock).not.toHaveBeenCalled()
    })

    it('rejects a missing path param without calling the server', async () => {
        const getComment = queryMaker({
            method: 'GET',
            path: '/v1/todos/:id/comments/:commentId',
            params: z.object({ id: z.string() }),
            response: z.unknown(),
        })

        await expect(getComment({ params: { id: '1' } })).rejects.toThrow(
            'Missing path parameter: commentId',
        )
        expect(fetchMock).not.toHaveBeenCalled()
    })

    it('throws a NetworkError when the server cannot be reached', async () => {
        fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))

        await expect(getTodo({ params: { id: '1' } })).rejects.toBeInstanceOf(NetworkError)
    })

    it('rethrows an abort as is', async () => {
        const controller = new AbortController()
        controller.abort()
        const abortError = new DOMException('Aborted', 'AbortError')
        fetchMock.mockRejectedValueOnce(abortError)

        await expect(getTodo({ params: { id: '1' }, signal: controller.signal })).rejects.toBe(
            abortError,
        )
    })

    it('throws a DecodeError when a 2xx body is not json', async () => {
        respond(200, '<html></html>', 'text/html')

        await expect(getTodo({ params: { id: '1' } })).rejects.toBeInstanceOf(DecodeError)
    })

    it('throws a DecodeError when a 2xx body does not match the response schema', async () => {
        respond(200, { id: 1 })

        await expect(getTodo({ params: { id: '1' } })).rejects.toBeInstanceOf(DecodeError)
    })

    it('accepts an empty response with z.void()', async () => {
        const deleteTodo = queryMaker({
            method: 'DELETE',
            path: '/v1/todos/:id',
            params: z.object({ id: z.string() }),
            response: z.void(),
        })
        fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))

        await expect(deleteTodo({ params: { id: '1' } })).resolves.toBeUndefined()
    })

    it('throws the problem as a typed error on a non-2xx response', async () => {
        respond(
            404,
            { type: 'about:blank', title: 'Not Found', status: 404, detail: 'Todo not found' },
            'application/problem+json',
        )

        const error = await getTodo({ params: { id: '1' } }).catch((e: unknown) => e)

        expect(error).toBeInstanceOf(HttpError)
        expect(error).toMatchObject({ _tag: 'NotFound', message: 'Todo not found' })
    })

    it('handles a non-2xx response that is not json', async () => {
        respond(502, 'Bad Gateway', 'text/plain')

        const error = await getTodo({ params: { id: '1' } }).catch((e: unknown) => e)

        expect(error).toMatchObject({ _tag: 'ServerError', message: 'Request failed (HTTP 502)' })
    })
})
