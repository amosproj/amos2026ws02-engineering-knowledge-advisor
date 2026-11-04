const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
})

export function formatDateTime(isoDate: string) {
    return dateTimeFormat.format(new Date(isoDate))
}
