import { describe, expect, it } from 'vitest'

import {
    MOUSE_PROFILES,
    activeModifier,
    buttonActions,
    profileBindings,
} from './mouse-profile-model'

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

describe('profileBindings', () => {
    it('lists the modifier bindings of each button and leaves unused buttons empty', () => {
        expect(profileBindings(MOUSE_PROFILES.blender)).toEqual({
            left: [],
            middle: [
                { input: 'Drag', action: 'rotate' },
                { input: 'Shift + drag', action: 'pan' },
                { input: 'Ctrl + drag', action: 'zoom' },
                { input: 'Scroll', action: 'zoom' },
            ],
            right: [],
        })
        expect(profileBindings(MOUSE_PROFILES.default).left).toEqual([
            { input: '', action: 'rotate' },
            { input: 'Shift +', action: 'pan' },
        ])
    })
})
