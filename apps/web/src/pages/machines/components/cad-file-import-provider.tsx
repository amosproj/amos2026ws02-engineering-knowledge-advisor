import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { CadFileImportContext, type ImportItem } from './cad-file-import-context'
import { createImports } from './cad-file-imports'

export function CadFileImportProvider({ children }: { children: React.ReactNode }) {
    const queryClient = useQueryClient()
    const [items, setItems] = useState<ImportItem[]>([])
    const [imports] = useState(() => createImports(queryClient, setItems))

    useEffect(() => {
        imports.setMounted(true)
        return () => imports.setMounted(false)
    }, [imports])

    // Prevent the user from closing the page while a file uploads.
    const isUploading = items.some((item) => item.phase === 'uploading')
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
