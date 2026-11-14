import multiprocessing
import os
import struct
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path

import pytest
from step_documents import DocumentBuilder, box

from cad_file_worker import conversion
from cad_file_worker.conversion import convert_step_file
from cad_file_worker.errors import ConversionTimeoutError, StopRequested
from services.cad.errors import StepImportError
from services.cad.model import CadModel

TIMEOUT = 60


def _crash(*_: object) -> None:
    os._exit(3)


def _hang(*_: object) -> None:
    time.sleep(TIMEOUT)


def _die_while_sending(_step: Path, _glb: Path, sender: Connection) -> None:
    os.write(sender.fileno(), struct.pack("!i", 100) + b"partial")
    os._exit(3)


def _hang_after_closing_the_pipe(_step: Path, _glb: Path, sender: Connection) -> None:
    sender.close()
    time.sleep(TIMEOUT)


def convert(
    step_path: Path, timeout: float = TIMEOUT, stopping: threading.Event | None = None
) -> CadModel:
    return convert_step_file(
        step_path,
        step_path.with_suffix(".glb"),
        timeout,
        stopping or threading.Event(),
        lambda: None,
    )


@pytest.fixture(autouse=True)
def no_child_left():
    yield
    assert multiprocessing.active_children() == []


def test_the_model_comes_back_without_its_document(tmp_path: Path):
    builder = DocumentBuilder()
    builder.part("Plate", box())
    step_path: Path = builder.write_step(tmp_path / "plate.step")

    model: CadModel = convert(step_path)

    assert [occ.name for occ in model.occurrences] == ["Plate"]
    assert model.document is None


def test_an_invalid_file_raises_the_parser_error(tmp_path: Path):
    step_path: Path = tmp_path / "invalid.step"
    step_path.write_text("not a step file")
    with pytest.raises(StepImportError, match="Could not read STEP file"):
        convert(step_path)


@pytest.mark.parametrize("target", [_crash, _die_while_sending])
def test_a_child_dying_without_its_result_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: Callable[..., None]
):
    monkeypatch.setattr(conversion, "_convert", target)
    with pytest.raises(StepImportError, match="exit code 3"):
        convert(tmp_path / "any.step")


@pytest.mark.parametrize("target", [_hang, _hang_after_closing_the_pipe])
def test_a_hanging_child_is_killed_after_the_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: Callable[..., None]
):
    monkeypatch.setattr(conversion, "_convert", target)
    with pytest.raises(ConversionTimeoutError):
        convert(tmp_path / "any.step", timeout=1)


def test_a_stop_kills_the_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(conversion, "_convert", _hang)
    stopping = threading.Event()
    threading.Timer(1, stopping.set).start()
    started: float = time.monotonic()
    with pytest.raises(StopRequested):
        convert(tmp_path / "any.step", stopping=stopping)
    assert time.monotonic() - started < TIMEOUT / 2
