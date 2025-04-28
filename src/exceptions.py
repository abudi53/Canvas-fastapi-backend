class AuthenticationError(Exception):
    """Custom exception for authentication failures."""

    def __init__(self, message: str = "Could not validate credentials"):
        self.message = message
        super().__init__(self.message)


class BadRequestError(Exception):
    """Custom exception for bad client requests."""

    def __init__(self, message: str = "Bad request"):
        self.message = message
        super().__init__(self.message)


class NotFoundError(Exception):
    """Custom exception for resource not found."""

    def __init__(self, resource: str = "Resource"):
        self.message = f"{resource} not found"
        super().__init__(self.message)
