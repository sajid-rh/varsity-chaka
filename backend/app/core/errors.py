"""Application errors that the API turns into the standard error envelope."""


class AppError(Exception):
    """A business-rule failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
