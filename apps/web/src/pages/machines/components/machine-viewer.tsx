import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Canvas } from '@react-three/fiber'

import { Button, Spinner, useSettings } from '@components'

import { errorCode } from '../models/machine-errors'
import type { ViewInset } from '../utils/camera-rig'
import { buildSketch, disposeSketch, type Sketch } from '../utils/machine-sketch'
import { SceneModel } from '../utils/scene-model'
import { ViewerLighting } from './viewer-lighting'
import { ViewerScene } from './viewer-scene'
import { ViewerToolbar } from './viewer-toolbar'

const FOV = 45

export type ViewState = {
    selected: string[]
    hidden: string[]
    isolated: string[] | undefined
}

/** ``sequence`` repeats a request for the same parts. */
export type FrameRequest = { targets: string[]; sequence: number }

type MachineViewerProps = {
    fileId: string
    inset: ViewInset
    view: ViewState
    frameRequest: FrameRequest | undefined
    onPick: (occurrenceIds: string[]) => void
    onMiss: () => void
}

export default function MachineViewer({
    fileId,
    inset,
    view,
    frameRequest,
    onPick,
    onMiss,
}: MachineViewerProps) {
    const model = useQuery({
        queryKey: ['models', fileId],
        queryFn: ({ signal }) => SceneModel.load(fileId, signal),
        staleTime: Infinity,
        gcTime: 0,
    })
    const [resetCount, setResetCount] = useState(0)
    const [settingsOpen, setSettingsOpen] = useState(false)
    const dragged = useRef(false)
    const data = model.data
    const { settings } = useSettings()
    const sketching = settings.selectionStyle === 'sketch'
    const [built, setBuilt] = useState<{ model: SceneModel; sketch: Sketch }>()
    // Releases the edges of a replaced model, the dispose effect below runs on the change
    if (built && built.model !== data) setBuilt(undefined)
    const sketch = sketching && built?.model === data ? built?.sketch : undefined

    useEffect(() => {
        if (!data) return
        return () => data.dispose()
    }, [data])

    useEffect(() => {
        if (!data?.sphere || !sketching || built?.model === data) return
        const controller = new AbortController()
        buildSketch(data.scene, data.meshes, controller.signal)
            .then((result) => setBuilt({ model: data, sketch: result }))
            // Without edges the selection stays opaque
            .catch(() => undefined)
        return () => controller.abort()
    }, [data, sketching, built])

    useEffect(() => {
        if (!built) return
        return () => disposeSketch(built.sketch)
    }, [built])

    if (model.isPending) {
        return (
            <Overlay inset={inset}>
                <Spinner />
            </Overlay>
        )
    }
    if (model.isError) {
        return errorCode(model.error) === 'model_unavailable' ? (
            <Overlay inset={inset}>No 3D model for this CAD file.</Overlay>
        ) : (
            <Overlay inset={inset}>
                <p>The 3D model could not be loaded.</p>
                <Button variant="outline" size="sm" onClick={() => void model.refetch()}>
                    Try again
                </Button>
            </Overlay>
        )
    }
    const { sphere } = model.data
    if (!sphere) {
        return <Overlay inset={inset}>The 3D model is empty.</Overlay>
    }

    return (
        <>
            <Canvas
                flat
                frameloop="demand"
                dpr={[1, 2]}
                camera={{ fov: FOV }}
                onPointerMissed={(event) => {
                    if (event.type === 'click' && !dragged.current) onMiss()
                }}
            >
                <ViewerLighting />
                <ViewerScene
                    model={model.data}
                    sphere={sphere}
                    inset={inset}
                    resetCount={resetCount}
                    view={view}
                    frameRequest={frameRequest}
                    sketch={sketch}
                    dragged={dragged}
                    onPick={onPick}
                    onMiss={onMiss}
                />
            </Canvas>
            <ViewerToolbar
                settingsOpen={settingsOpen}
                onSettingsOpenChange={setSettingsOpen}
                onReset={() => setResetCount((count) => count + 1)}
            />
        </>
    )
}

function Overlay({ inset, children }: { inset: ViewInset; children: React.ReactNode }) {
    return (
        <div
            className="text-muted-foreground absolute inset-y-0 flex flex-col items-center justify-center gap-2 text-sm"
            style={{ left: inset.left, right: inset.right }}
        >
            {children}
        </div>
    )
}
