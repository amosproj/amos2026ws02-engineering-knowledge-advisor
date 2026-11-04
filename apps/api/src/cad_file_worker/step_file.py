import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

# it turns out that step fies start with a ISO-10303-21 header and end with an END-ISO-10303-21 footer
# we can check for those markers to validate the file without parsing it fully
HEADER = b"ISO-10303-21;"
FOOTER = b"END-ISO-10303-21;"
UTF8_BOM = b"\xef\xbb\xbf"

# Room for the whitespace allowed before the header and after the footer
EDGE_SIZE = 4096


@dataclass(frozen=True)
class StepFileScan:
    sha256: str
    is_valid: bool


def scan_step_file(chunks: Iterable[bytes]) -> StepFileScan:
    """Hash a STEP file in one pass and check its header and footer markers."""
    digest = hashlib.sha256()
    head = b""
    tail = b""
    for chunk in chunks:
        digest.update(chunk)
        if len(head) < EDGE_SIZE:
            head += chunk[: EDGE_SIZE - len(head)]
        tail = (tail + chunk[-EDGE_SIZE:])[-EDGE_SIZE:]

    is_valid = head.removeprefix(UTF8_BOM).lstrip().startswith(
        HEADER
    ) and tail.rstrip().endswith(FOOTER)
    return StepFileScan(sha256=digest.hexdigest(), is_valid=is_valid)
