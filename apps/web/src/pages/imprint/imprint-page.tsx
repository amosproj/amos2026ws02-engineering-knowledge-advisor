import { ScrollArea } from '@components'

export function ImprintPage() {
    return (
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 md:px-6 md:py-10">
            <div className="space-y-1">
                <h1 className="text-2xl font-semibold tracking-tight">Imprint</h1>
                <p className="text-muted-foreground text-sm">
                    Information according to legal requirements.
                </p>
            </div>

            <ScrollArea className="bg-card max-h-[calc(100vh-20rem)] rounded-lg border p-6">
                <div className="space-y-6 text-sm leading-relaxed">
                    <section>
                        <h2 className="mb-2 text-base font-semibold">Publisher</h2>
                        <p>
                            Your Company Name
                            <br />
                            Street Address 1
                            <br />
                            12345 City
                            <br />
                            Country
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-2 text-base font-semibold">Contact</h2>
                        <p>
                            Email: contact@example.com
                            <br />
                            Phone: +49 (0) 123 456789
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-2 text-base font-semibold">Responsible for Content</h2>
                        <p>
                            Max Mustermann
                            <br />
                            Street Address 1
                            <br />
                            12345 City
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-2 text-base font-semibold">Disclaimer</h2>
                        <p>
                            The information provided on this application is made with great care.
                            However, we cannot guarantee the accuracy, completeness, or timeliness
                            of the content. As a service provider, we are responsible for our own
                            content on these pages in accordance with general legislation.
                        </p>
                    </section>
                </div>
            </ScrollArea>
        </div>
    )
}
