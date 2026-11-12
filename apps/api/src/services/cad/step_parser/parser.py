import codecs
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.Standard import Standard_Failure
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPControl import STEPControl_Controller
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDocStd import TDocStd_Document

from services.cad.errors import StepImportError
from services.cad.model import CadModel
from services.cad.step_parser.document_walker import DocumentWalker

READ_CHUNK_SIZE: int = 1 << 20

_codepage_lock = threading.Lock()


def is_utf8(path: Path) -> bool:
    decoder = codecs.getincrementaldecoder("utf-8")()
    with path.open("rb") as file:
        try:
            while chunk := file.read(READ_CHUNK_SIZE):
                decoder.decode(chunk)
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            return False
    return True


@contextmanager
def step_codepage(codepage: str) -> Iterator[None]:
    """Temporarily set the codepage used to decode STEP strings"""
    with _codepage_lock:
        STEPControl_Controller.Init_s()
        previous: str = Interface_Static.CVal_s("read.step.codepage")
        Interface_Static.SetCVal_s("read.step.codepage", codepage)
        try:
            yield
        finally:
            Interface_Static.SetCVal_s("read.step.codepage", previous)


class StepParser:
    """Turn a STEP file into a ``CadModel`` of definitions and occurrences.

    Normalizations:
    - a component that only wraps unnamed geometry of its parent part is merged into that part
    - parts without faces (points, curves) are dropped.
    """

    def parse(self, path: str | Path) -> CadModel:
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            raise StepImportError(f"Input file not found: {path}")

        document = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        reader.SetColorMode(True)
        try:
            codepage: str = "UTF8" if is_utf8(path) else "CP1252"
        except OSError as error:
            raise StepImportError(f"Could not read STEP file: {path}") from error
        with step_codepage(codepage):
            self._read(reader, path)
            self._transfer(reader, document, path)
        return self.parse_document(document, path.name)

    @staticmethod
    def _read(reader: STEPCAFControl_Reader, path: Path) -> None:
        try:
            status = reader.ReadFile(str(path))
        except (OSError, Standard_Failure) as error:
            raise StepImportError(f"Could not read STEP file: {path}") from error
        if status != IFSelect_RetDone:
            raise StepImportError(f"Could not read STEP file: {path}")

    @staticmethod
    def _transfer(
        reader: STEPCAFControl_Reader, document: TDocStd_Document, path: Path
    ) -> None:
        try:
            transferred: bool = reader.Transfer(document)
        except Standard_Failure as error:
            raise StepImportError(f"Could not transfer STEP data: {path}") from error
        if not transferred:
            raise StepImportError(f"Could not transfer STEP data: {path}")

    def parse_document(self, document: TDocStd_Document, source_name: str) -> CadModel:
        return DocumentWalker(document, source_name).walk()
