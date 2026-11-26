"""The JSON chunk of a binary glTF (GLB) file, read and rewritten in place."""

import json
import struct
from collections.abc import Mapping
from pathlib import Path

from services import JsonObject, JsonValue
from services.cad.errors import GlbGenerationError

MAGIC: bytes = b"glTF"
VERSION: int = 2
JSON_CHUNK: int = 0x4E4F534A
HEADER_SIZE: int = 12
CHUNK_HEADER_SIZE: int = 8
ERROR_MALFORMED: str = "malformed glTF: {key!r} is not of type {expected}"


def read_glb(path: Path) -> tuple[JsonObject, bytes]:
    """The JSON chunk, parsed, and every byte after it, as stored."""
    data: bytes = path.read_bytes()
    if len(data) < HEADER_SIZE + CHUNK_HEADER_SIZE or data[:4] != MAGIC:
        raise GlbGenerationError(f"Not a GLB file: {path.name}")
    length, chunk_type = struct.unpack_from("<II", data, HEADER_SIZE)
    if chunk_type != JSON_CHUNK:
        raise GlbGenerationError(f"GLB file without JSON chunk: {path.name}")
    start: int = HEADER_SIZE + CHUNK_HEADER_SIZE
    gltf: JsonObject = _expect(
        json.loads(data[start : start + length]), dict, "JSON chunk"
    )
    return gltf, data[start + length :]


def write_glb(path: Path, gltf: Mapping[str, JsonValue], rest: bytes) -> None:
    """Writes ``gltf`` as the JSON chunk, followed by ``rest`` from ``read_glb``."""
    text: bytes = json.dumps(gltf, ensure_ascii=False, separators=(",", ":")).encode()
    # chunks are 4-byte aligned, the JSON chunk with spaces
    text += b" " * (-len(text) % 4)
    body: bytes = struct.pack("<II", len(text), JSON_CHUNK) + text + rest
    path.write_bytes(
        MAGIC + struct.pack("<II", VERSION, HEADER_SIZE + len(body)) + body
    )


def get_objects(container: Mapping[str, JsonValue], key: str) -> list[JsonObject]:
    return [_expect(item, dict, key) for item in _get_list(container, key)]


def get_ints(container: Mapping[str, JsonValue], key: str) -> list[int]:
    return [_expect(item, int, key) for item in _get_list(container, key)]


def get_int(container: Mapping[str, JsonValue], key: str) -> int | None:
    value: JsonValue = container.get(key)
    return None if value is None else _expect(value, int, key)


def get_str(container: Mapping[str, JsonValue], key: str) -> str:
    return _expect(container.get(key, ""), str, key)


def ensure_object(container: JsonObject, key: str) -> JsonObject:
    return _expect(container.setdefault(key, {}), dict, key)


def ensure_list(container: JsonObject, key: str) -> list[JsonValue]:
    return _expect(container.setdefault(key, []), list, key)


def _get_list(container: Mapping[str, JsonValue], key: str) -> list[JsonValue]:
    return _expect(container.get(key, []), list, key)


def _expect[T](value: JsonValue, kind: type[T], key: str) -> T:
    if not isinstance(value, kind):
        raise GlbGenerationError(
            ERROR_MALFORMED.format(key=key, expected=kind.__name__)
        )
    return value
