"""Where the files of a CAD file are stored: one folder per CAD file."""

import posixpath

SOURCE_FILE_NAME: str = "source.step"
MACHINES_PREFIX: str = "machines/"


def get_source_key(machine_id: str, assembly_group_id: str, cad_file_id: str) -> str:
    """Key of the uploaded STEP file. Its preview and 3D model will sit in the same folder."""
    return (
        f"{MACHINES_PREFIX}{machine_id}/assembly-groups/{assembly_group_id}"
        f"/cad-files/{cad_file_id}/{SOURCE_FILE_NAME}"
    )


def get_folder(source_key: str) -> str:
    """The folder of a CAD file, with its source and anything derived from it."""
    return posixpath.dirname(source_key) + "/"


def get_cad_file_id(key: str) -> str | None:
    """The CAD file id in machines/{machine}/assembly-groups/{group}/cad-files/{cad_file}/..."""
    parts: list[str] = key.split("/")
    if len(parts) < 7 or parts[2] != "assembly-groups" or parts[4] != "cad-files":
        return None
    return parts[5]
