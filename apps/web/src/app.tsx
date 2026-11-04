import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { ThemeProvider, Toaster, TooltipProvider } from '@components'
import { CadFileImportProvider } from '@pages/machines/components/cad-file-import-provider'
import { queryClient } from '@queries/query-config'
import { router } from '@pages/router'

export function App() {
    return (
        <ThemeProvider>
            <TooltipProvider>
                <QueryClientProvider client={queryClient}>
                    <Toaster>
                        <CadFileImportProvider>
                            <RouterProvider
                                router={router}
                                context={{
                                    queryClient,
                                }}
                            />
                        </CadFileImportProvider>
                    </Toaster>
                </QueryClientProvider>
            </TooltipProvider>
        </ThemeProvider>
    )
}
