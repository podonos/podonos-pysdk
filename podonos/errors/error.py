class NotSupportedError(Exception):
    """Exception raised for unsupported operations."""

    def __init__(self, message: str = "This operation is not supported"):
        self.message = message
        super().__init__(self.message)


class InvalidFileError(Exception):
    """Exception raised for invalid file input."""

    def __init__(self, message: str = "This file is invalid"):
        self.message = message
        super().__init__(self.message)
