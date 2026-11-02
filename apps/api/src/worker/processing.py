import time
from collections.abc import Callable, Iterator
from contextlib import closing
from typing import Any

from psycopg import errors as pg_errors
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import Machine, MachineStatus, get_engine
from logger import logger
from storage.s3 import delete_object_quietly, open_object
from worker.step_file import StepFileScan, scan_step_file

CHUNK_SIZE = 8 * 1024 * 1024
MAX_PROCESSING_SECONDS = 30 * 60
SHA256_UNIQUE_INDEX = "uq_machines_sha256_ready"


def process_next_machine(on_progress: Callable[[], None]) -> bool:
    """Check the STEP file of the machine waiting longest in processing.

    The row stays locked until its new status is committed, so other workers skip it and a
    crash hands it back to the next run. Returns False when no machine is waiting.
    """
    with Session(get_engine()) as session:
        machine = session.scalars(
            select(Machine)
            .where(Machine.status == MachineStatus.PROCESSING)
            .order_by(Machine.updated_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if machine is None:
            return False

        machine_id, object_key = machine.id, machine.object_key
        logger.info(f"Processing machine {machine_id}")
        try:
            error_code = _check_file(session, machine, on_progress)
        except Exception:
            session.rollback()
            # Move it to the back of the queue so it does not block the other machines
            session.execute(
                update(Machine)
                .where(Machine.id == machine_id)
                .values(updated_at=func.now())
            )
            session.commit()
            raise

    if error_code is None:
        logger.info(f"Machine {machine_id} is ready")
    else:
        logger.info(f"Machine {machine_id} failed: {error_code}")
        if error_code != "upload_not_found":
            delete_object_quietly(object_key)
    return True


def _check_file(
    session: Session, machine: Machine, on_progress: Callable[[], None]
) -> str | None:
    """Commit the outcome of the check and return its error code, None when ready."""
    body = open_object(machine.object_key)
    if body is None:
        return _fail(session, machine, "upload_not_found")
    with closing(body):
        scan = scan_step_file(_read_chunks(body, on_progress))
    if not scan.is_valid:
        return _fail(session, machine, "invalid_step_file")

    try:
        with session.begin_nested():
            _mark_ready(machine, scan)
    except IntegrityError as error:
        if not _violates_sha256_index(error):
            raise
        return _fail(session, machine, "duplicate_file")
    session.commit()
    return None


def _read_chunks(body: Any, on_progress: Callable[[], None]) -> Iterator[bytes]:
    deadline = time.monotonic() + MAX_PROCESSING_SECONDS
    for chunk in body.iter_chunks(CHUNK_SIZE):
        if time.monotonic() > deadline:
            raise TimeoutError("Reading the STEP file took too long")
        on_progress()
        yield chunk


def _mark_ready(machine: Machine, scan: StepFileScan) -> None:
    machine.status = MachineStatus.READY
    machine.sha256 = scan.sha256
    machine.error_code = None


def _fail(session: Session, machine: Machine, error_code: str) -> str:
    machine.status = MachineStatus.FAILED
    machine.error_code = error_code
    session.commit()
    return error_code


def _violates_sha256_index(error: IntegrityError) -> bool:
    return (
        isinstance(error.orig, pg_errors.UniqueViolation)
        and error.orig.diag.constraint_name == SHA256_UNIQUE_INDEX
    )
