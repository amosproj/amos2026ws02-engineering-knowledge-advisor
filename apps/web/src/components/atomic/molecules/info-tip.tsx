import * as React from 'react'
import { InformationCircleIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'

import { Button } from '../atoms/button'
import { Popover, PopoverContent, PopoverDescription, PopoverTrigger } from './popover'

type InfoTipProps = {
    label: string
    children: React.ReactNode
    descriptionId?: string
}

function InfoTip({ label, children, descriptionId }: InfoTipProps) {
    return (
        <>
            <Popover>
                <PopoverTrigger
                    openOnHover
                    delay={200}
                    render={
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            aria-label={label}
                            className="text-muted-foreground"
                        />
                    }
                >
                    <HugeiconsIcon icon={InformationCircleIcon} strokeWidth={2} />
                </PopoverTrigger>
                <PopoverContent
                    aria-label={label}
                    side="top"
                    className="w-64 gap-0 rounded-xl px-3 py-2 text-xs"
                >
                    <PopoverDescription>{children}</PopoverDescription>
                </PopoverContent>
            </Popover>
            {descriptionId ? (
                <span hidden id={descriptionId}>
                    {children}
                </span>
            ) : null}
        </>
    )
}

export { InfoTip }
