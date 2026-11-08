import {
    Skeleton,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@components'

import type { Machine } from '../query/machine-api'
import { StatusBadge } from './status-badge'

const COLUMNS = 6

type MachinesTableProps = {
    machines: Machine[] | undefined
}

export function MachinesTable({ machines }: MachinesTableProps) {
    return (
        <Table>
            <TableHeader>
                <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Identifier</TableHead>
                    <TableHead>Customer</TableHead>
                    <TableHead className="text-right">Groups</TableHead>
                    <TableHead className="text-right">Files</TableHead>
                    <TableHead>Status</TableHead>
                </TableRow>
            </TableHeader>
            <TableBody>
                {machines
                    ? machines.map((machine) => (
                          <TableRow key={machine.id}>
                              <TableCell className="max-w-64">
                                  <p className="truncate font-medium">{machine.name}</p>
                                  {machine.description ? (
                                      <p className="text-muted-foreground truncate">
                                          {machine.description}
                                      </p>
                                  ) : null}
                              </TableCell>
                              <TableCell>{machine.identifier}</TableCell>
                              <TableCell className="max-w-48 truncate">
                                  {machine.customer}
                              </TableCell>
                              <TableCell className="text-right tabular-nums">
                                  {machine.assembly_group_count}
                              </TableCell>
                              <TableCell className="text-right tabular-nums">
                                  {machine.cad_file_count}
                              </TableCell>
                              <TableCell>
                                  <StatusBadge status={machine.status} />
                              </TableCell>
                          </TableRow>
                      ))
                    : Array.from({ length: 5 }, (_, index) => (
                          <TableRow key={index}>
                              {Array.from({ length: COLUMNS }, (_, cell) => (
                                  <TableCell key={cell}>
                                      <Skeleton className="h-5 w-full" />
                                  </TableCell>
                              ))}
                          </TableRow>
                      ))}
            </TableBody>
        </Table>
    )
}
