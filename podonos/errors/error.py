class NotSupportedError(Exception):
    """Exception raised for unsupported operations."""
    def __init__(self, message="This operation is not supported"):
        self.message = message
        super().__init__(self.message)
