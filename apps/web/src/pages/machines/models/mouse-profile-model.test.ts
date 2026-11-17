import { describe, expect, it } from 'vitest'

import { MOUSE_PROFILES, activeModifier, buttonActions } from './mouse-profile-model'

describe('buttonActions', () => {
    it('uses the action bound to the held modifier', () => {
        expect(buttonActions(MOUSE_PROFILES.blender, 'shift').middle).toBe('pan')
        expect(buttonActions(MOUSE_PROFILES.blender, 'ctrl').middle).toBe('zoom')
    })

    it('falls back to the plain action when the modifier is not bound', () => {
        expect(buttonActions(MOUSE_PROFILES.autocad, 'ctrl').middle).toBe('pan')
    })
})

describe('activeModifier', () => {
    it('prefers Ctrl when Shift is also held', () => {
        expect(activeModifier({ shiftKey: true, ctrlKey: true })).toBe('ctrl')
    })
})
