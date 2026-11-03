import { MoreHorizontalIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import {
    Button,
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@components'

export type Action = {
    label: string
    onSelect: () => void
    destructive?: boolean
    disabled?: boolean
}

type ActionsMenuProps = {
    // Accessible name of the menu button, e.g. "Actions of Robot cell"
    label: string
    actions: Action[]
    size?: 'icon' | 'icon-sm'
}

export function ActionsMenu({ label, actions, size = 'icon' }: ActionsMenuProps) {
    return (
        <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="secondary" size={size} aria-label={label} />}>
                <HugeiconsIcon icon={MoreHorizontalIcon} strokeWidth={2} />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
                {actions.map((action) => (
                    <DropdownMenuItem
                        key={action.label}
                        variant={action.destructive ? 'destructive' : 'default'}
                        disabled={action.disabled}
                        onClick={action.onSelect}
                    >
                        {action.label}
                    </DropdownMenuItem>
                ))}
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
