import * as React from 'react'
import { Cancel01Icon, File01Icon, Upload04Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/react'
import { cn } from 'cn'

import {
    formatFileSize,
    getFileKey,
    selectFiles,
    type FileCandidate,
    type FileRejection,
} from './file-validation'
import {
    Attachment,
    AttachmentAction,
    AttachmentActions,
    AttachmentContent,
    AttachmentDescription,
    AttachmentMedia,
    AttachmentTitle,
} from '../../molecules/attachment'
import { FieldError } from '../../molecules/field'

type FileUploadBaseProps = {
    id?: string
    className?: string
    /** Extensions (`.stp, .jt`) or MIME types (`image/png`, `image/*`). */
    accept?: readonly string[]
    /** Maximum size of a single file, in bytes. */
    maxSize?: number
    disabled?: boolean
    invalid?: boolean
    onBlur?: () => void
    'aria-describedby'?: string
}

type FileUploadSingleProps = {
    mode: 'single'
    value: File | null
    onChange: (file: File | null) => void
    maxFiles?: never
}

type FileUploadMultipleProps = {
    mode: 'multiple'
    value: File[]
    onChange: (files: File[]) => void
    maxFiles?: number
}

export type FileUploadProps = FileUploadBaseProps &
    (FileUploadSingleProps | FileUploadMultipleProps)

function hasDraggedFiles(event: { dataTransfer: DataTransfer | null }) {
    return event.dataTransfer?.types.includes('Files') ?? false
}

function getDroppedCandidates(dataTransfer: DataTransfer): FileCandidate[] {
    return Array.from(dataTransfer.items).flatMap((item) => {
        const file = item.kind === 'file' ? item.getAsFile() : null

        return file ? [{ file, isDirectory: item.webkitGetAsEntry()?.isDirectory ?? false }] : []
    })
}

function getHint({ mode, accept, maxSize, maxFiles }: FileUploadProps) {
    const parts = [
        accept?.length ? accept.join(', ') : null,
        maxSize !== undefined ? `up to ${formatFileSize(maxSize)}` : null,
        mode === 'multiple' && maxFiles !== undefined ? `${maxFiles} files max` : null,
    ]

    return parts.filter(Boolean).join(' · ')
}

function FileUpload(props: FileUploadProps) {
    const { id, className, accept, maxSize, maxFiles, disabled, invalid, onBlur } = props

    const generatedId = React.useId()
    const zoneId = id ?? `${generatedId}-zone`
    const hintId = `${zoneId}-hint`
    const errorId = `${zoneId}-error`

    const inputRef = React.useRef<HTMLInputElement>(null)
    const zoneRef = React.useRef<HTMLButtonElement>(null)
    const dragDepth = React.useRef(0)

    const [isDragActive, setIsDragActive] = React.useState(false)
    const [rejections, setRejections] = React.useState<FileRejection[]>([])

    const files = props.mode === 'single' ? (props.value ? [props.value] : []) : props.value
    const hint = getHint(props)

    React.useEffect(() => {
        const preventFileNavigation = (event: DragEvent) => {
            if (hasDraggedFiles(event)) {
                event.preventDefault()
            }
        }

        window.addEventListener('dragover', preventFileNavigation)
        window.addEventListener('drop', preventFileNavigation)

        return () => {
            window.removeEventListener('dragover', preventFileNavigation)
            window.removeEventListener('drop', preventFileNavigation)
        }
    }, [])

    const commit = (next: File[]) => {
        if (props.mode === 'single') {
            props.onChange(next[0] ?? null)
        } else {
            props.onChange(next)
        }
    }

    const handleCandidates = (candidates: FileCandidate[]) => {
        if (candidates.length === 0) {
            return
        }

        const result = selectFiles(candidates, {
            mode: props.mode,
            current: files,
            accept,
            maxSize,
            maxFiles,
        })

        setRejections(result.rejections)

        if (result.files.some((file, index) => file !== files[index])) {
            commit(result.files)
        }
    }

    const handleRemove = (key: string) => {
        setRejections([])
        commit(files.filter((file) => getFileKey(file) !== key))
        zoneRef.current?.focus()
    }

    const handleDragEnter = (event: React.DragEvent) => {
        if (disabled || !hasDraggedFiles(event)) {
            return
        }

        event.preventDefault()
        dragDepth.current += 1
        setIsDragActive(true)
    }

    const handleDragOver = (event: React.DragEvent) => {
        if (!hasDraggedFiles(event)) {
            return
        }

        event.preventDefault()
        event.dataTransfer.dropEffect = disabled ? 'none' : 'copy'
    }

    const handleDragLeave = () => {
        if (dragDepth.current === 0) {
            return
        }

        dragDepth.current -= 1

        if (dragDepth.current === 0) {
            setIsDragActive(false)
        }
    }

    const handleDrop = (event: React.DragEvent) => {
        if (!hasDraggedFiles(event)) {
            return
        }

        event.preventDefault()
        dragDepth.current = 0
        setIsDragActive(false)

        if (!disabled) {
            handleCandidates(getDroppedCandidates(event.dataTransfer))
        }
    }

    const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        handleCandidates(
            Array.from(event.target.files ?? []).map((file) => ({ file, isDirectory: false })),
        )
        event.target.value = ''
    }

    const describedBy =
        [props['aria-describedby'], hint ? hintId : null, rejections.length > 0 ? errorId : null]
            .filter(Boolean)
            .join(' ') || undefined

    return (
        <div data-slot="file-upload" className={cn('flex w-full flex-col gap-2', className)}>
            <div
                onDragEnter={handleDragEnter}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
            >
                <input
                    ref={inputRef}
                    type="file"
                    hidden
                    tabIndex={-1}
                    accept={accept?.join(',')}
                    multiple={props.mode === 'multiple'}
                    disabled={disabled}
                    onChange={handleInputChange}
                />
                <button
                    ref={zoneRef}
                    id={zoneId}
                    type="button"
                    disabled={disabled}
                    data-slot="file-upload-zone"
                    data-drag-active={isDragActive || undefined}
                    data-invalid={invalid || rejections.length > 0 || undefined}
                    aria-invalid={invalid || rejections.length > 0 || undefined}
                    aria-describedby={describedBy}
                    onClick={() => inputRef.current?.click()}
                    onBlur={onBlur}
                    className={cn(
                        'flex w-full flex-col items-center gap-2',
                        'rounded-2xl border border-dashed px-4 py-8',
                        'border-input hover:bg-muted/50 data-drag-active:border-primary data-drag-active:bg-muted data-invalid:border-destructive',
                        'text-center text-sm',
                        'focus-visible:border-ring focus-visible:ring-ring/30 transition-colors outline-none focus-visible:ring-3 disabled:pointer-events-none disabled:opacity-50',
                    )}
                >
                    <span className="bg-muted text-foreground flex size-10 items-center justify-center rounded-lg">
                        <HugeiconsIcon icon={Upload04Icon} strokeWidth={2} aria-hidden="true" />
                    </span>
                    <span className="text-foreground font-medium">
                        {props.mode === 'single'
                            ? 'Drag and drop a file here, or click to browse'
                            : 'Drag and drop files here, or click to browse'}
                    </span>
                    {hint ? (
                        <span id={hintId} className="text-muted-foreground text-xs">
                            {hint}
                        </span>
                    ) : null}
                </button>
            </div>
            {files.length > 0 ? (
                <div
                    data-slot="file-upload-list"
                    className="flex max-h-48 flex-col gap-2 overflow-y-auto"
                >
                    {files.map((file) => {
                        const key = getFileKey(file)

                        return (
                            <Attachment key={key} className="w-full">
                                <AttachmentMedia>
                                    <HugeiconsIcon
                                        icon={File01Icon}
                                        strokeWidth={2}
                                        aria-hidden="true"
                                    />
                                </AttachmentMedia>
                                <AttachmentContent>
                                    <AttachmentTitle title={file.name}>{file.name}</AttachmentTitle>
                                    <AttachmentDescription>
                                        {formatFileSize(file.size)}
                                    </AttachmentDescription>
                                </AttachmentContent>
                                <AttachmentActions>
                                    <AttachmentAction
                                        type="button"
                                        disabled={disabled}
                                        aria-label={`Remove ${file.name}`}
                                        onClick={() => handleRemove(key)}
                                    >
                                        <HugeiconsIcon
                                            icon={Cancel01Icon}
                                            strokeWidth={2}
                                            aria-hidden="true"
                                        />
                                    </AttachmentAction>
                                </AttachmentActions>
                            </Attachment>
                        )
                    })}
                </div>
            ) : null}
            <FieldError
                id={errorId}
                errors={rejections.map((rejection) => ({ message: rejection.message }))}
            />
        </div>
    )
}

export { FileUpload }
