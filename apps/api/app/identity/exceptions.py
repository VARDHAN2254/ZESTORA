"""Identity domain exceptions for user registration, authentication, and status checks."""


class IdentityError(Exception):
    """Base exception for identity and user domain errors."""


class UserAlreadyExistsError(IdentityError):
    """Raised when attempting to register an email address that is already registered."""


class InvalidCredentialsError(IdentityError):
    """Raised when authentication fails due to incorrect email or password.

    Generic error to avoid disclosing whether an email address exists.
    """


class AccountNotActiveError(IdentityError):
    """Raised when an inactive or suspended user attempts to authenticate or perform operations."""

    def __init__(
        self, message: str = "Account is not active.", status: str | None = None
    ) -> None:
        self.status = status
        super().__init__(message)


class UserNotFoundError(IdentityError):
    """Raised when a specified user entity does not exist."""
