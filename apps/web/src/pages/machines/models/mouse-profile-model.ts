export type MouseAction = 'rotate' | 'pan' | 'zoom' | 'none'
export type MouseButton = 'left' | 'middle' | 'right'
export type Modifier = 'plain' | 'shift' | 'ctrl'

type ButtonActions = { plain: MouseAction; shift?: MouseAction; ctrl?: MouseAction }

export type MouseProfile = {
    label: string
    requiresMiddleButton: boolean
    buttons: Record<MouseButton, ButtonActions>
    wheel: MouseAction
}

export const MOUSE_PROFILE_IDS = [
    'default',
    'blender',
    'autocad',
    'inventor',
    'solidworks',
    'fusion360',
] as const

export type MouseProfileId = (typeof MOUSE_PROFILE_IDS)[number]

const MIDDLE_PAN_SHIFT_ROTATE: MouseProfile['buttons'] = {
    left: { plain: 'none' },
    middle: { plain: 'pan', shift: 'rotate' },
    right: { plain: 'none' },
}

export const MOUSE_PROFILES: Record<MouseProfileId, MouseProfile> = {
    default: {
        label: 'Default',
        requiresMiddleButton: false,
        buttons: {
            left: { plain: 'rotate', shift: 'pan' },
            middle: { plain: 'pan' },
            right: { plain: 'pan' },
        },
        wheel: 'zoom',
    },
    blender: {
        label: 'Blender',
        requiresMiddleButton: true,
        buttons: {
            left: { plain: 'none' },
            middle: { plain: 'rotate', shift: 'pan', ctrl: 'zoom' },
            right: { plain: 'none' },
        },
        wheel: 'zoom',
    },
    autocad: {
        label: 'AutoCAD',
        requiresMiddleButton: true,
        buttons: MIDDLE_PAN_SHIFT_ROTATE,
        wheel: 'zoom',
    },
    inventor: {
        label: 'Inventor',
        requiresMiddleButton: true,
        buttons: MIDDLE_PAN_SHIFT_ROTATE,
        wheel: 'zoom',
    },
    solidworks: {
        label: 'SolidWorks',
        requiresMiddleButton: true,
        buttons: {
            left: { plain: 'none' },
            middle: { plain: 'rotate', shift: 'zoom', ctrl: 'pan' },
            right: { plain: 'none' },
        },
        wheel: 'zoom',
    },
    fusion360: {
        label: 'Fusion 360',
        requiresMiddleButton: true,
        buttons: MIDDLE_PAN_SHIFT_ROTATE,
        wheel: 'zoom',
    },
}

export function activeModifier(event: { shiftKey: boolean; ctrlKey: boolean }): Modifier {
    if (event.ctrlKey) return 'ctrl'
    if (event.shiftKey) return 'shift'
    return 'plain'
}

export function buttonActions(profile: MouseProfile, modifier: Modifier) {
    const pick = (actions: ButtonActions) =>
        (modifier !== 'plain' && actions[modifier]) || actions.plain

    return {
        left: pick(profile.buttons.left),
        middle: pick(profile.buttons.middle),
        right: pick(profile.buttons.right),
        wheel: profile.wheel,
    }
}

export type Binding = { input: string; action: MouseAction }

const MODIFIERS = ['plain', 'shift', 'ctrl'] as const

const INPUT_LABELS = {
    button: { plain: '', shift: 'Shift +', ctrl: 'Ctrl +' },
    wheel: { plain: 'Drag', shift: 'Shift + drag', ctrl: 'Ctrl + drag' },
}

export function profileBindings(profile: MouseProfile): Record<MouseButton, Binding[]> {
    const bindings = (button: MouseButton) => {
        const labels = INPUT_LABELS[button === 'middle' ? 'wheel' : 'button']
        return MODIFIERS.flatMap((modifier) => {
            const action = profile.buttons[button][modifier]
            return action && action !== 'none' ? [{ input: labels[modifier], action }] : []
        })
    }
    const scroll = profile.wheel === 'none' ? [] : [{ input: 'Scroll', action: profile.wheel }]

    return {
        left: bindings('left'),
        middle: [...bindings('middle'), ...scroll],
        right: bindings('right'),
    }
}
