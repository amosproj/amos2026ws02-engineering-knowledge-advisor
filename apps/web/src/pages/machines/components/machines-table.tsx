import {
    Skeleton,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@components'
import { formatFileSize } from '@components/atomic/organisms/file-upload/file-validation'

import type { Machine } from '../query/machine-api'
import { formatDateTime } from './format-date-time'
import { useMachineImport } from './machine-import-context'
import { MachineStatusBadge } from './machine-status-badge'

type MachinesTableProps = {
    machines: Machine[] | undefined
    onOpen: (machineId: string) => void
}

export function MachinesTable({ machines, onOpen }: MachinesTableProps) {
    const { activeImport } = useMachineImport()

    return (
        <Table>
            <TableHeader>
                <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>File</TableHead>
                    <TableHead>Imported</TableHead>
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
                              <TableCell>
                                  <MachineStatusBadge
                                      status={machine.status}
                                      activeImport={
                                          activeImport?.machineId === machine.id
                                              ? activeImport
                                              : null
                                      }
                                  />
                              </TableCell>
                              <TableCell className="max-w-56">
                                  <p className="truncate">{machine.original_filename}</p>
                                  <p className="text-muted-foreground">
                                      {formatFileSize(machine.size_bytes)}
                                  </p>
                              </TableCell>
                              <TableCell className="text-muted-foreground">
                                  {formatDateTime(machine.created_at)}
                              </TableCell>
                          </TableRow>
                      ))
                    : Array.from({ length: 5 }, (_, index) => (
                          <TableRow key={index}>
                              {Array.from({ length: 4 }, (_, cell) => (
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
