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
    onOpen: (machineId: string) => void
}

export function MachinesTable({ machines, onOpen }: MachinesTableProps) {
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
                          // The name button carries the keyboard access, the row only widens the click area
                          <TableRow
                              key={machine.id}
                              className="cursor-pointer"
                              onClick={() => onOpen(machine.id)}
                          >
                              <TableCell className="max-w-64">
                                  <button
                                      type="button"
                                      className="focus-visible:ring-ring/50 block max-w-full truncate rounded-sm text-left font-medium hover:underline focus-visible:ring-[3px] focus-visible:outline-none"
                                  >
                                      {machine.name}
                                  </button>
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
