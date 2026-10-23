import type { ReactNode } from 'react'

export function SettingsSection({ title, children }: { title: string; children: ReactNode }) {
    return (
        <section className="space-y-3">
            <h2 className="text-base font-medium">{title}</h2>
            <div className="space-y-3">{children}</div>
        </section>
    )
}

export function SettingsRow({
    title,
    description,
    children,
}: {
    title: string
    description: string
    children: ReactNode
}) {
    return (
        <div className="bg-card flex items-center justify-between gap-6 rounded-xl border px-5 py-4">
            <div className="space-y-1">
                <p className="text-sm font-medium">{title}</p>
                <p className="text-muted-foreground text-sm">{description}</p>
            </div>
            <div className="shrink-0">{children}</div>
        </div>
    )
}
