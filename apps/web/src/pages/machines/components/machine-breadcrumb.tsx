import { useQuery } from '@tanstack/react-query'

import { Skeleton } from '@components'

import { machineQuery } from '../query/machine-api'

export function MachineBreadcrumb({ params }: { params: Record<string, string> }) {
    const { data: machine, isError } = useQuery(machineQuery(params.machineId))

    if (machine) return machine.name
    if (isError) return 'Unknown machine'
    return <Skeleton className="h-4 w-24" />
}
