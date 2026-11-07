class NotFoundError(LookupError):
    """No record of the expected class has this id."""


class CadFileConflictError(Exception):
    """The CAD file cannot be changed in its current state. ``error_code`` tells the client why."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code: str | None = error_code


class BusyError(CadFileConflictError):
    """The worker holds a CAD file of the request for a moment."""

    def __init__(self) -> None:
        super().__init__("A CAD file is being processed. Please try again.")


class UploadNotFoundError(CadFileConflictError):
    def __init__(self) -> None:
        super().__init__("The CAD file has not been uploaded.", "upload_not_found")


class UploadExistsError(CadFileConflictError):
    def __init__(self) -> None:
        super().__init__(
            "The file is being processed or is ready already.", "upload_exists"
        )


class ImportFailedError(CadFileConflictError):
    def __init__(self, error_code: str | None) -> None:
        super().__init__("The CAD file import failed.", error_code)
