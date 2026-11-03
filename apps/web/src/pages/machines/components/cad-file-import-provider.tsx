import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { CadFileImportContext, isCancellable, type ImportItem } from './cad-file-import-context'
import { createImportQueue } from './cad-file-import-queue'

export function CadFileImportProvider({ children }: { children: React.ReactNode }) {
    const queryClient = useQueryClient()
    const [items, setItems] = useState<ImportItem[]>([])
    const [imports] = useState(() => createImportQueue(queryClient, setItems))

    useEffect(() => {
        imports.setMounted(true)
        return () => imports.setMounted(false)
    }, [imports])

    // Prevent the user from closing the page while a file is waiting or uploading.
    const isUploading = items.some(isCancellable)
    useEffect(() => {
        if (!isUploading) return
        const warn = (event: BeforeUnloadEvent) => event.preventDefault()
        window.addEventListener('beforeunload', warn)
        return () => window.removeEventListener('beforeunload', warn)
    }, [isUploading])

    const value = useMemo(
        () => ({ items, startImport: imports.start, cancelImport: imports.cancel }),
        [items, imports],
    )

    return <CadFileImportContext.Provider value={value}>{children}</CadFileImportContext.Provider>
}
