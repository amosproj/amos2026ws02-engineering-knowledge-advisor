import { describe, expect, it } from 'vitest'
import { formatFileSize, matchesAccept, selectFiles, type FileCandidate } from './file-validation'

function makeFile(name: string, content = 'data', type = '') {
    return new File([content], name, { type, lastModified: 1 })
}

function candidate(file: File, isDirectory = false): FileCandidate {
    return { file, isDirectory }
}

function codes(result: ReturnType<typeof selectFiles>) {
    return result.rejections.map((rejection) => rejection.code)
}

describe('formatFileSize', () => {
    it('formats bytes with the largest fitting unit', () => {
        expect(formatFileSize(0)).toBe('0 B')
        expect(formatFileSize(1536)).toBe('1.5 KB')
        expect(formatFileSize(500 * 1024 * 1024)).toBe('500 MB')
    })
})

describe('matchesAccept', () => {
    it('accepts everything without a filter', () => {
        expect(matchesAccept(makeFile('a.bin'), undefined)).toBe(true)
        expect(matchesAccept(makeFile('a.bin'), [])).toBe(true)
    })

    it('matches extensions case-insensitively even with an empty MIME type', () => {
        expect(matchesAccept(makeFile('PART.STP'), ['.stp'])).toBe(true)
        expect(matchesAccept(makeFile('part.step'), ['.stp'])).toBe(false)
    })

    it('matches exact and wildcard MIME types', () => {
        const image = makeFile('a.png', 'data', 'image/png')

        expect(matchesAccept(image, ['image/png'])).toBe(true)
        expect(matchesAccept(image, ['image/*'])).toBe(true)
        expect(matchesAccept(image, ['video/*'])).toBe(false)
    })
})

describe('selectFiles in single mode', () => {
    const accept = ['.stp']

    it('replaces the current file with a valid one', () => {
        const next = makeFile('b.stp')
        const result = selectFiles([candidate(next)], {
            mode: 'single',
            current: [makeFile('a.stp')],
            accept,
        })

        expect(result.files).toEqual([next])
        expect(result.rejections).toEqual([])
    })

    it('rejects the whole batch when several files are dropped', () => {
        const current = makeFile('a.stp')
        const result = selectFiles([candidate(makeFile('b.stp')), candidate(makeFile('c.stp'))], {
            mode: 'single',
            current: [current],
            accept,
        })

        expect(result.files).toEqual([current])
        expect(codes(result)).toEqual(['too-many-files'])
    })

    it('keeps the current file when the new one is invalid', () => {
        const current = makeFile('a.stp')
        const result = selectFiles([candidate(makeFile('b.txt'))], {
            mode: 'single',
            current: [current],
            accept,
        })

        expect(result.files).toEqual([current])
        expect(codes(result)).toEqual(['invalid-type'])
    })

    it('does nothing without candidates', () => {
        expect(selectFiles([], { mode: 'single', current: [] })).toEqual({
            files: [],
            rejections: [],
        })
    })
})

describe('selectFiles rejections', () => {
    it.each([
        ['directory', candidate(makeFile('folder'), true)],
        ['invalid-type', candidate(makeFile('a.txt'))],
        ['empty-file', candidate(makeFile('a.stp', ''))],
        ['too-large', candidate(makeFile('a.stp', 'too large'))],
    ])('reports %s', (code, input) => {
        const result = selectFiles([input], {
            mode: 'multiple',
            current: [],
            accept: ['.stp'],
            maxSize: 4,
        })

        expect(result.files).toEqual([])
        expect(codes(result)).toEqual([code])
    })

    it('accepts a file exactly at the size limit', () => {
        const file = makeFile('a.stp', 'data')

        expect(
            selectFiles([candidate(file)], { mode: 'multiple', current: [], maxSize: 4 }).files,
        ).toEqual([file])
    })
})

describe('selectFiles in multiple mode', () => {
    it('keeps valid files and reports the invalid ones', () => {
        const valid = makeFile('a.stp')
        const result = selectFiles([candidate(valid), candidate(makeFile('b.txt'))], {
            mode: 'multiple',
            current: [],
            accept: ['.stp'],
        })

        expect(result.files).toEqual([valid])
        expect(codes(result)).toEqual(['invalid-type'])
    })

    it('rejects duplicates of current files and within the batch', () => {
        const current = makeFile('a.stp')
        const result = selectFiles(
            [
                candidate(makeFile('a.stp')),
                candidate(makeFile('b.stp')),
                candidate(makeFile('b.stp')),
            ],
            { mode: 'multiple', current: [current] },
        )

        expect(result.files.map((file) => file.name)).toEqual(['a.stp', 'b.stp'])
        expect(codes(result)).toEqual(['duplicate', 'duplicate'])
    })

    it('rejects files beyond maxFiles', () => {
        const result = selectFiles([candidate(makeFile('a.stp')), candidate(makeFile('b.stp'))], {
            mode: 'multiple',
            current: [],
            maxFiles: 1,
        })

        expect(result.files.map((file) => file.name)).toEqual(['a.stp'])
        expect(codes(result)).toEqual(['too-many-files'])
    })
})
