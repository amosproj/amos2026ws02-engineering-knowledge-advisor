import * as React from 'react'
import { FieldLabel, InfoTip } from '../atomic/molecules'

type FormLabelProps = {
    htmlFor: string
    label: string
    optional?: boolean
    info?: string
    infoId?: string
    action?: React.ReactNode
}

export function FormLabel({ htmlFor, label, optional, info, infoId, action }: FormLabelProps) {
    const heading = (
        <div className="flex items-center gap-1">
            <FieldLabel htmlFor={htmlFor}>
                {label}
                {optional ? (
                    <span className="text-muted-foreground font-normal"> (optional)</span>
                ) : null}
            </FieldLabel>
            {info ? (
                <InfoTip label={`More about ${label}`} descriptionId={infoId}>
                    {info}
                </InfoTip>
            ) : null}
        </div>
    )

    if (!action) return heading

    return (
        <div className="flex items-center justify-between gap-3">
            {heading}
            {action}
        </div>
    )
}
