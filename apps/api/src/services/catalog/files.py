"""Where the files of a CAD file are stored: one folder per CAD file."""

import posixpath

SOURCE_FILE_NAME: str = "source.step"
FILES_PREFIX: str = "files/"


def get_source_key(cad_file_id: str) -> str:
    """Key of the uploaded STEP file. Its preview and 3D model will sit in the same folder."""
    return f"{FILES_PREFIX}{cad_file_id}/{SOURCE_FILE_NAME}"


def get_folder(source_key: str) -> str:
    """The folder of a CAD file, with its source and anything derived from it."""
    return posixpath.dirname(source_key) + "/"


def get_cad_file_id(key: str) -> str | None:
    """The CAD file id in files/{cad_file}/..."""
    parts: list[str] = key.split("/")
    if len(parts) < 3 or f"{parts[0]}/" != FILES_PREFIX or not parts[1]:
        return None
    return parts[1]
