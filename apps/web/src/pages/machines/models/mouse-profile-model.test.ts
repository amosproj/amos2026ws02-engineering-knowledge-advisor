import { describe, expect, it } from 'vitest'

import { MOUSE_PROFILES, activeModifier, buttonActions } from './mouse-profile-model'

describe('buttonActions', () => {
    it('uses the action bound to the held modifier', () => {
        expect(buttonActions(MOUSE_PROFILES.blender, 'shift').middle).toBe('pan')
        expect(buttonActions(MOUSE_PROFILES.blender, 'ctrl').middle).toBe('zoom')
    })
})

describe('activeModifier', () => {
    it('prefers Ctrl when Shift is also held', () => {
        expect(activeModifier({ shiftKey: true, ctrlKey: true })).toBe('ctrl')
    })
})
