export type MouseAction = 'rotate' | 'pan' | 'zoom' | 'none'

export type MouseProfile = {
    left: MouseAction
    middle: MouseAction
    right: MouseAction
    wheel: MouseAction
}

export const DEFAULT_MOUSE_PROFILE: MouseProfile = {
    left: 'rotate',
    middle: 'pan',
    right: 'pan',
    wheel: 'zoom',
}
