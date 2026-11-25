class StopRequested(Exception):
    """The worker is shutting down: the file is left in processing for the next start."""


class ChildTimeoutError(Exception):
    """The child process took longer than allowed."""


class ConversionTimeoutError(Exception):
    """The STEP file took longer to convert than allowed."""
