import { MutationObserver, type QueryKey } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { queryClient } from './query-config'
import { DecodeError, HttpError, NetworkError } from './query-errors'

describe('retry', () => {
    const retry = queryClient.getDefaultOptions().queries!.retry as (
        failureCount: number,
        error: Error,
    ) => boolean

    it.each([
        ['a network error', new NetworkError(new TypeError('Failed to fetch')), true],
        ['a server error', new HttpError('ServerError', 503, 'Service Unavailable'), true],
        ['a client error', new HttpError('NotFound', 404, 'Not Found'), false],
        ['a decode error', new DecodeError(new Error()), false],
    ])('retries %s: %s', (_label, error, expected) => {
        expect(retry(0, error)).toBe(expected)
    })

    it('retries only once', () => {
        expect(retry(1, new NetworkError(new TypeError('Failed to fetch')))).toBe(false)
    })
})

describe('invalidation', () => {
    const invalidates: QueryKey[] = [['todos'], ['stats']]

    afterEach(() => {
        vi.restoreAllMocks()
    })

    function run(mutationFn: () => Promise<unknown>, invalidateOnError?: boolean) {
        const invalidate = vi.spyOn(queryClient, 'invalidateQueries').mockResolvedValue()
        const observer = new MutationObserver(queryClient, {
            mutationFn,
            meta: { invalidates, invalidateOnError },
        })
        return { invalidate, mutate: () => observer.mutate().catch(() => {}) }
    }

    it('invalidates the declared queries on success', async () => {
        const { invalidate, mutate } = run(() => Promise.resolve('ok'))

        await mutate()

        expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual(invalidates)
    })

    it('does not invalidate on error by default', async () => {
        const { invalidate, mutate } = run(() => Promise.reject(new Error('failed')))

        await mutate()

        expect(invalidate).not.toHaveBeenCalled()
    })

    it('invalidates on error with invalidateOnError', async () => {
        const { invalidate, mutate } = run(() => Promise.reject(new Error('failed')), true)

        await mutate()

        expect(invalidate).toHaveBeenCalledTimes(invalidates.length)
    })
})
