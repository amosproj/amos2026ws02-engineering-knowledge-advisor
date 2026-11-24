import { ScrollArea } from '@components'

export function PrivacyPolicyPage() {
    return (
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 md:px-6 md:py-10">
            <div className="space-y-1">
                <h1 className="text-2xl font-semibold tracking-tight">Privacy Policy</h1>
                <p className="text-muted-foreground text-sm">
                    This notice describes the application's current data handling. The operator must
                    add deployment-specific details below.
                </p>
            </div>

            <ScrollArea className="bg-card max-h-[calc(100vh-20rem)] rounded-lg border p-6">
                <div className="space-y-6 text-sm leading-relaxed">
                    <section>
                        <h2 className="mb-2 text-base font-semibold">Operator</h2>
                        <p>
                            The operator of this deployment decides why and how personal data is
                            processed. Contact them with questions or requests:
                        </p>
                        <p className="mt-2">
                            [Operator name and address]
                            <br />
                            [Privacy contact email]
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-2 text-base font-semibold">
                            What the application stores
                        </h2>
                        <p>
                            The application has no user accounts. It stores engineering knowledge
                            records and their metadata (for example, record type, links, and text)
                            in PostgreSQL. Uploaded CAD files and documents, plus generated 3D
                            models, are stored in MinIO object storage. The browser uploads files
                            directly to that storage using a temporary upload form provided by the
                            API. The API also stores upload status and file metadata in PostgreSQL.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-2 text-base font-semibold">
                            AI requests, logs, and deletion
                        </h2>
                        <p>
                            If the chat API is used, the submitted messages are sent to the
                            configured language model provider to generate a response. The
                            application does not save chat conversations. API and CAD worker logs
                            record operational events and errors; log content and retention depend
                            on the deployment. Records and files remain until deleted by a user or
                            operator. Deleting a record removes its associated files where
                            applicable; related knowledge records may instead be marked for review.
                            The operator controls backups and their retention.
                        </p>
                    </section>

                    <section>
                        <h2 className="mb-2 text-base font-semibold">
                            Deployment details and your rights
                        </h2>
                        <p>
                            The operator must provide its purposes and legal bases, contact details,
                            configured service providers and any international data transfers, and
                            applicable retention periods. Contact the operator above to ask about
                            your data or exercise your rights. You may also lodge a complaint with
                            the competent data protection supervisory authority. The operator should
                            add that authority's contact details for this deployment.
                        </p>
                    </section>
                </div>
            </ScrollArea>
        </div>
    )
}
