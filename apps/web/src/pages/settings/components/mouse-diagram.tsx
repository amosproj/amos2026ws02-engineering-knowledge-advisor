import {
    profileBindings,
    type Binding,
    type MouseAction,
    type MouseButton,
    type MouseProfile,
} from '@pages/machines/models/mouse-profile-model'

const ACTION_LABELS: Record<MouseAction, string> = {
    rotate: 'Rotate',
    pan: 'Pan',
    zoom: 'Zoom',
    none: 'None',
}

const BUTTON_NAMES: Record<MouseButton, string> = {
    left: 'Left button',
    middle: 'Wheel',
    right: 'Right button',
}

const BODY_PATH =
    'M180 20C222 20 230 60 230 100V160C230 198 208 214 180 214C152 214 130 198 130 160V100C130 60 138 20 180 20Z'

type Callout = {
    dot: [number, number]
    leader: string
    x: number
    y: number
    anchor: 'start' | 'end'
}

const CALLOUTS: Record<MouseButton, Callout> = {
    left: { dot: [152, 66], leader: 'M152 66L120 34H100', x: 94, y: 34, anchor: 'end' },
    right: { dot: [208, 66], leader: 'M208 66L240 34H260', x: 266, y: 34, anchor: 'start' },
    middle: { dot: [180, 55], leader: 'M180 55L245 156H260', x: 266, y: 156, anchor: 'start' },
}

const LINE_HEIGHT = 16

function describe(bindings: Binding[]) {
    if (bindings.length === 0) return 'Unused'
    return bindings
        .map((binding) => `${binding.input} ${ACTION_LABELS[binding.action]}`.trim())
        .join(', ')
}

function buttonClass(used: boolean) {
    return used ? 'fill-primary/15 stroke-primary' : 'fill-muted stroke-border'
}

function ButtonCallout({ button, bindings }: { button: MouseButton; bindings: Binding[] }) {
    const { dot, leader, x, y, anchor } = CALLOUTS[button]
    const firstLine = y + 4 - ((Math.max(bindings.length, 1) - 1) * LINE_HEIGHT) / 2

    return (
        <g>
            <path d={leader} className="stroke-muted-foreground fill-none" />
            <circle cx={dot[0]} cy={dot[1]} r={2.5} className="fill-foreground" />
            {bindings.length === 0 ? (
                <text
                    x={x}
                    y={firstLine}
                    textAnchor={anchor}
                    className="fill-muted-foreground italic"
                >
                    Unused
                </text>
            ) : (
                bindings.map((binding, index) => (
                    <text
                        key={binding.input}
                        x={x}
                        y={firstLine + index * LINE_HEIGHT}
                        textAnchor={anchor}
                        className="fill-foreground"
                    >
                        {binding.input ? (
                            <tspan className="fill-muted-foreground">{binding.input} </tspan>
                        ) : null}
                        {ACTION_LABELS[binding.action]}
                    </text>
                ))
            )}
        </g>
    )
}

export function MouseDiagram({ profile }: { profile: MouseProfile }) {
    const bindings = profileBindings(profile)
    const buttons = ['left', 'middle', 'right'] as const

    return (
        <>
            <svg
                viewBox="0 10 400 215"
                aria-hidden
                className="mx-auto block w-full max-w-md [stroke-width:1.5] text-xs [stroke-linejoin:round]"
            >
                <path d={BODY_PATH} className="fill-card stroke-border" />
                <path
                    d="M171 27C150 29 137 52 137 92Q137 96 141 96H167Q171 96 171 92Z"
                    className={buttonClass(bindings.left.length > 0)}
                />
                <path
                    d="M189 27C210 29 223 52 223 92Q223 96 219 96H193Q189 96 189 92Z"
                    className={buttonClass(bindings.right.length > 0)}
                />
                <rect
                    x={174}
                    y={38}
                    width={12}
                    height={32}
                    rx={6}
                    className={buttonClass(bindings.middle.length > 0)}
                />
                <g className="[stroke-width:1]">
                    {buttons.map((button) => (
                        <ButtonCallout key={button} button={button} bindings={bindings[button]} />
                    ))}
                </g>
            </svg>
            <ul className="sr-only">
                {buttons.map((button) => (
                    <li key={button}>
                        {BUTTON_NAMES[button]}: {describe(bindings[button])}
                    </li>
                ))}
            </ul>
        </>
    )
}
