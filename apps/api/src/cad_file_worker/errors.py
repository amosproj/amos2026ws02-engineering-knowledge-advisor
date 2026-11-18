class StopRequested(Exception):
    """The worker is shutting down: the file is left in processing for the next start."""


class ConversionTimeoutError(Exception):
    """The STEP file took longer to convert than allowed."""
