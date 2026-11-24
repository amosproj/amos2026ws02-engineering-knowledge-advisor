import { queryOptions } from '@tanstack/react-query'

async function fetchNotices(signal?: AbortSignal) {
    const response = await fetch('/THIRD_PARTY_NOTICES.txt', { signal })
    if (!response.ok) throw new Error('Failed to load legal notices')
    return response.text()
}

export const legalNoticesQuery = queryOptions({
    queryKey: ['notices', 'third-party'],
    queryFn: ({ signal }) => fetchNotices(signal),
    staleTime: Infinity,
})
