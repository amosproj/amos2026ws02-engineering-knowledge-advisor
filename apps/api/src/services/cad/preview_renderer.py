from pathlib import Path

import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
from vtkmodules.vtkCommonCore import vtkLogger
from vtkmodules.vtkIOImage import vtkPNGWriter
from vtkmodules.vtkIOImport import vtkGLTFImporter
from vtkmodules.vtkRenderingCore import (
    vtkCamera,
    vtkLight,
    vtkRenderer,
    vtkRenderWindow,
    vtkWindowToImageFilter,
)

from services.cad.errors import PreviewError

WIDTH: int = 512
HEIGHT: int = 384

# same direction as the first view of the 3D viewer (Y-up like the GLB)
VIEW_DIRECTION: tuple[float, float, float] = (1.0, 0.8, 1.0)

LIGHT_INTENSITY: float = 2.0
FILLED_SHARE: float = 0.95
ANTIALIASING_SAMPLES: int = 4


def render_preview(glb_path: Path, png_path: Path) -> None:
    """Renders the whole GLB scene to a PNG with a transparent background.

    Run it in a child process: VTK crashes the process when no OpenGL is available.

    Raises:
        PreviewError: the scene is empty or the PNG could not be written.
    """
    # without a display VTK warns about X11 before it falls back to EGL
    vtkLogger.SetStderrVerbosity(vtkLogger.VERBOSITY_ERROR)
    window = vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetSize(WIDTH, HEIGHT)
    window.SetMultiSamples(ANTIALIASING_SAMPLES)
    window.SetAlphaBitPlanes(1)
    renderer = vtkRenderer()
    renderer.SetBackgroundAlpha(0.0)
    window.AddRenderer(renderer)

    importer = vtkGLTFImporter()
    importer.SetFileName(str(glb_path))
    importer.SetRenderWindow(window)
    if not importer.Update() or renderer.VisibleActorCount() == 0:
        raise PreviewError(f"Nothing to render in {glb_path.name}")

    light = vtkLight()
    light.SetLightTypeToHeadlight()
    light.SetIntensity(LIGHT_INTENSITY)
    renderer.RemoveAllLights()
    renderer.AddLight(light)

    camera: vtkCamera = renderer.GetActiveCamera()
    camera.SetFocalPoint(0.0, 0.0, 0.0)
    camera.SetPosition(*VIEW_DIRECTION)
    camera.SetViewUp(0.0, 1.0, 0.0)
    renderer.ResetCamera()
    renderer.ResetCameraScreenSpace(FILLED_SHARE)
    window.Render()

    image = vtkWindowToImageFilter()
    image.SetInput(window)
    image.SetInputBufferTypeToRGBA()
    image.ReadFrontBufferOff()
    image.ShouldRerenderOff()
    writer = vtkPNGWriter()
    writer.SetFileName(str(png_path))
    writer.SetInputConnection(image.GetOutputPort())
    writer.Write()
    if writer.GetErrorCode() != 0:
        raise PreviewError(f"Could not write {png_path.name}")
