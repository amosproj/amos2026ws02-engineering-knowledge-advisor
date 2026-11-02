import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from '@tanstack/react-router'
import { ThemeProvider, Toaster, TooltipProvider } from '@components'
import { MachineImportProvider } from '@pages/machines/components/machine-import-provider'
import { queryClient } from '@queries/query-config'
import { router } from '@pages/router'

export function App() {
    return (
        <ThemeProvider>
            <TooltipProvider>
                <QueryClientProvider client={queryClient}>
                    <Toaster>
                        <MachineImportProvider>
                            <RouterProvider
                                router={router}
                                context={{
                                    queryClient,
                                }}
                            />
                        </MachineImportProvider>
                    </Toaster>
                </QueryClientProvider>
            </TooltipProvider>
        </ThemeProvider>
    )
}
