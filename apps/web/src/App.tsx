import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './queries/query-config'
import { RouterProvider } from '@tanstack/react-router'
import { router } from './pages/router'

export function App() {
    return (
        <QueryClientProvider client={queryClient}>
            <RouterProvider
                router={router}
                context={{
                    queryClient,
                }}
            />
        </QueryClientProvider>
    )
}
