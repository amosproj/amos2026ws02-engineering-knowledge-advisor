import type { ReactNode } from 'react'

export function SettingsSection({ title, children }: { title: string; children: ReactNode }) {
    return (
        <section className="space-y-3">
            <h2 className="text-base font-medium">{title}</h2>
            <div className="bg-card divide-y rounded-xl border">{children}</div>
        </section>
    )
}

export function SettingsRow({
    title,
    description,
    info,
    children,
}: {
    title: string
    description?: string
    info?: ReactNode
    children: ReactNode
}) {
    return (
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-5 py-3">
            <div className="min-w-0 flex-1 basis-36 space-y-0.5">
                <div className="flex items-center gap-1">
                    <p className="text-sm font-medium">{title}</p>
                    {info}
                </div>
                {description ? (
                    <p className="text-muted-foreground text-sm">{description}</p>
                ) : null}
            </div>
            <div className="shrink-0">{children}</div>
        </div>
    )
}
