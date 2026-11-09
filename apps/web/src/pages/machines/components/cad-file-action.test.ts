import { describe, expect, it } from 'vitest'

import { toCadFileAction } from './cad-file-action'

const cadFile = { '@id': 'cad-1', '@type': 'CadFile', name: 'cell.step' }

describe('toCadFileAction', () => {
    it('uploads a first file', () => {
        expect(toCadFileAction('empty', undefined)).toEqual({ kind: 'upload' })
    })

    it('replaces a ready file', () => {
        expect(toCadFileAction('ready', cadFile)).toEqual({
            kind: 'replace',
            cadFileId: 'cad-1',
            name: 'cell.step',
        })
    })

    it('offers nothing while the file is processed', () => {
        expect(toCadFileAction('processing', cadFile)).toBeNull()
    })

    it('uploads again a failed, interrupted or missing upload into the same record', () => {
        expect(toCadFileAction('failed', cadFile)).toMatchObject({
            kind: 'retry',
            interrupted: false,
        })
        expect(toCadFileAction('empty', cadFile)).toMatchObject({
            kind: 'retry',
            interrupted: false,
        })
        expect(toCadFileAction('uploading', cadFile)).toEqual({
            kind: 'retry',
            cadFileId: 'cad-1',
            interrupted: true,
        })
    })
})
