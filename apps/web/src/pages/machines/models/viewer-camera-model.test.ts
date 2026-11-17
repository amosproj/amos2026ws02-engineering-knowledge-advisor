import { describe, expect, it } from 'vitest'

import { fitDistance } from './viewer-camera-model'

describe('fitDistance', () => {
    it('backs away further when the panels leave a narrow visible area', () => {
        const wide = fitDistance(1, 45, 1200, 800)
        const narrow = fitDistance(1, 45, 400, 800)

        expect(narrow).toBeGreaterThan(wide)
    })
})
