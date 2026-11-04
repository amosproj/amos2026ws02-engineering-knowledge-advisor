from abc import ABC, abstractmethod
from pathlib import Path

from cad.cad_file import CadFile


class CadFileParser(ABC):
    @abstractmethod
    def parse_file(self, file_identifier: str, path: str | Path) -> CadFile:
        pass
