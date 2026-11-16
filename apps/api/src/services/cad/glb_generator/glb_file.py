"""The JSON chunk of a binary glTF (GLB) file, read and rewritten in place."""

import json
import struct
from pathlib import Path
from typing import Any

from services.cad.errors import GlbGenerationError

MAGIC: bytes = b"glTF"
VERSION: int = 2
JSON_CHUNK: int = 0x4E4F534A
HEADER_SIZE: int = 12
CHUNK_HEADER_SIZE: int = 8


def read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    """The JSON chunk, parsed, and every byte after it, as stored."""
    data: bytes = path.read_bytes()
    if len(data) < HEADER_SIZE + CHUNK_HEADER_SIZE or data[:4] != MAGIC:
        raise GlbGenerationError(f"Not a GLB file: {path.name}")
    length, chunk_type = struct.unpack_from("<II", data, HEADER_SIZE)
    if chunk_type != JSON_CHUNK:
        raise GlbGenerationError(f"GLB file without JSON chunk: {path.name}")
    start: int = HEADER_SIZE + CHUNK_HEADER_SIZE
    return json.loads(data[start : start + length]), data[start + length :]


def write_glb(path: Path, gltf: dict[str, Any], rest: bytes) -> None:
    """Writes ``gltf`` as the JSON chunk, followed by ``rest`` from ``read_glb``."""
    text: bytes = json.dumps(gltf, ensure_ascii=False, separators=(",", ":")).encode()
    # chunks are 4-byte aligned, the JSON chunk with spaces
    text += b" " * (-len(text) % 4)
    body: bytes = struct.pack("<II", len(text), JSON_CHUNK) + text + rest
    path.write_bytes(
        MAGIC + struct.pack("<II", VERSION, HEADER_SIZE + len(body)) + body
    )
