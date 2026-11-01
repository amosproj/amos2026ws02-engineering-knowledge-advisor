import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { ThemeProvider, Toaster, TooltipProvider } from '@components'
import { queryClient } from '@queries/query-config'
import { router } from '@pages/router'

export function App() {
    return (
        <ThemeProvider>
            <TooltipProvider>
                <QueryClientProvider client={queryClient}>
                    <Toaster>
                        <RouterProvider
                            router={router}
                            context={{
                                queryClient,
                            }}
                        />
                    </Toaster>
                </QueryClientProvider>
            </TooltipProvider>
        </ThemeProvider>
    )
}
