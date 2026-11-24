import { useQuery } from '@tanstack/react-query'
import { ScrollArea } from '@components'
import { thirdPartyNoticesQuery } from './query/third-party-notices-api.ts'

export function ThirdPartyNoticesPage() {
    const { data, isLoading, error } = useQuery(thirdPartyNoticesQuery)

    return (
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 md:px-6 md:py-10">
            <div className="space-y-1">
                <h1 className="text-2xl font-semibold tracking-tight">Third-Party Notices</h1>
                <p className="text-muted-foreground text-sm">
                    This software depends on external packages and source code. All applicable
                    license and copyright information is listed below.
                </p>
            </div>

            {isLoading && <p className="text-muted-foreground">Loading notices...</p>}
            {error && <p className="text-destructive">Failed to load notices.</p>}
            {data && (
                <ScrollArea className="bg-card max-h-[calc(100vh-20rem)] rounded-lg border p-4">
                    <pre className="font-mono text-xs leading-relaxed whitespace-pre-wrap">
                        {data}
                    </pre>
                </ScrollArea>
            )}
        </div>
    )
}
