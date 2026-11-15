import { useQuery } from '@tanstack/react-query'

import { machineQuery } from '../query/machine-api'

export function MachineBreadcrumb({ params }: { params: Record<string, string> }) {
    const { data } = useQuery(machineQuery(params.machineId))
    return data?.record.name ?? 'Machine'
}
