import { useEffect } from 'react'
import { useThree } from '@react-three/fiber'
import { PMREMGenerator } from 'three'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'

export function ViewerLighting() {
    const get = useThree((state) => state.get)

    useEffect(() => {
        const { gl, scene } = get()
        const pmrem = new PMREMGenerator(gl)
        const room = new RoomEnvironment()
        const environment = pmrem.fromScene(room, 0.04)
        scene.environment = environment.texture
        scene.environmentIntensity = 0.7
        room.dispose()
        pmrem.dispose()
        return () => {
            scene.environment = null
            environment.dispose()
        }
    }, [get])

    return <directionalLight position={[1, 2, 1.5]} intensity={0.8} />
}
