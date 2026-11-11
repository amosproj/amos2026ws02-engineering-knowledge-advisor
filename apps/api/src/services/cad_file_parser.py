from abc import abstractmethod
from pathlib import Path
from typing import Protocol

from services.cad.cad_file import CadFile


class CadFileParser(Protocol):
    @abstractmethod
    def parse_file(self, file_identifier: str, path: str | Path) -> CadFile:
        """Reads a CAD file at ``path`` and returns a parsed ``CadFile`` with identifier set to ``file_identifier``."""
        ...
