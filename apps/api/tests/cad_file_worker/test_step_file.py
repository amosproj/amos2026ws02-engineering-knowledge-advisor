import hashlib

import pytest

from cad_file_worker.step_file import scan_step_file

STEP = b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def chunked(data: bytes, size: int = 7) -> list[bytes]:
    return [data[i : i + size] for i in range(0, len(data), size)]


def test_hashes_the_whole_file_across_chunks():
    scan = scan_step_file(chunked(STEP))

    assert scan.is_valid
    assert scan.sha256 == hashlib.sha256(STEP).hexdigest()


def test_accepts_a_bom_and_surrounding_whitespace():
    assert scan_step_file(chunked(b"\xef\xbb\xbf \r\n" + STEP + b"\r\n\n")).is_valid


@pytest.mark.parametrize(
    "data",
    [
        STEP[: -len(b"END-ISO-10303-21;\n")],
        b"solid cube\n" + STEP,
        STEP + b"garbage",
        b"",
    ],
    ids=["truncated", "not a step header", "data after the footer", "empty"],
)
def test_rejects_invalid_files(data):
    assert not scan_step_file(chunked(data)).is_valid
