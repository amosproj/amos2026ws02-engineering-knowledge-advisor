import { MutationCache, QueryClient, type QueryKey } from '@tanstack/react-query'
import { HttpError, NetworkError } from './query-errors'

export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            // Only transient failures are worth retrying.
            retry: (failureCount, error) =>
                (error instanceof NetworkError ||
                    (error instanceof HttpError && error._tag === 'ServerError')) &&
                failureCount < 1,
            staleTime: 5_000,
            refetchOnWindowFocus: false,
        },
    },
    mutationCache: new MutationCache({
        onError: async (_error, _variables, _onMutateResult, mutation, context) => {
            if (!mutation.meta?.invalidateOnError) return

            await Promise.all(
                (mutation.meta.invalidates ?? []).map((queryKey) =>
                    context.client.invalidateQueries({ queryKey }),
                ),
            )
        },
        onSuccess: async (_data, _variables, _onMutateResult, mutation, context) => {
            await Promise.all(
                (mutation.meta?.invalidates ?? []).map((queryKey) =>
                    context.client.invalidateQueries({ queryKey }),
                ),
            )
        },
    }),
})

declare module '@tanstack/react-query' {
    interface Register {
        mutationMeta: {
            invalidates?: readonly QueryKey[]
            /** Also invalidate when the server may have changed state before failing. */
            invalidateOnError?: boolean
        }
    }
}
