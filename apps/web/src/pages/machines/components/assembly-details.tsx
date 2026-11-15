import { useQuery } from '@tanstack/react-query'

import { Button, Skeleton } from '@components'

import { formatDimensions, type AssemblyNode } from '../models/assembly-tree-model'
import { assemblyGroupQuery } from '../query/machine-api'

type AssemblyDetailsProps = {
    node: AssemblyNode
    machineName: string
}

export function AssemblyDetails({ node, machineName }: AssemblyDetailsProps) {
    const group = useQuery({ ...assemblyGroupQuery(node.groupId ?? ''), enabled: !!node.groupId })

    return (
        <div className="grid gap-1 p-1 text-sm">
            {!node.groupId ? (
                <p className="text-muted-foreground">
                    The assembly group of this instance no longer exists.
                </p>
            ) : group.isPending ? (
                <div className="grid gap-2">
                    <Skeleton className="h-5 w-3/4" />
                    <Skeleton className="h-5 w-1/2" />
                </div>
            ) : group.isError ? (
                <div className="grid gap-2">
                    <p className="text-destructive">The assembly group could not be loaded.</p>
                    <Button
                        variant="outline"
                        size="sm"
                        className="justify-self-start"
                        onClick={() => void group.refetch()}
                    >
                        Try again
                    </Button>
                </div>
            ) : (
                <dl className="grid">
                    <Detail label="Assembly group">{group.data.name}</Detail>
                    {group.data.identifier ? (
                        <Detail label="Identifier">{group.data.identifier}</Detail>
                    ) : null}
                    {group.data.description ? (
                        <Detail label="Description">{group.data.description}</Detail>
                    ) : null}
                    <Detail label="Dimensions">{formatDimensions(group.data) ?? '—'}</Detail>
                </dl>
            )}
            <dl className="grid">
                <Detail label="Instance">{node.name}</Detail>
                <Detail label="Machine">{machineName}</Detail>
            </dl>
            <div className="text-muted-foreground mt-2 rounded-lg border border-dashed p-4 text-center">
                The knowledge capture form could be placed here.
            </div>
        </div>
    )
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="grid grid-cols-[7rem_1fr] gap-x-3 py-1.5">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="min-w-0 wrap-anywhere">{children}</dd>
        </div>
    )
}
