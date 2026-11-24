export function ThirdPartyNoticesPage() {
    return (
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 md:px-6 md:py-10">
            <div className="space-y-1">
                <h1 className="text-2xl font-semibold tracking-tight">Third-Party Notices</h1>
                <p className="text-muted-foreground text-sm">
                    This software depends on external packages and source code. All applicable
                    license and copyright information is listed below.
                </p>
            </div>

            <p className="text-sm">
                <a
                    href="/THIRD_PARTY_NOTICES.txt"
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary underline underline-offset-4"
                >
                    View full third-party notices (THIRD_PARTY_NOTICES.txt)
                </a>
            </p>
        </div>
    )
}
