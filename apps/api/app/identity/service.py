"""Identity service orchestrating customer registration, credential verification, and tokens."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.identity.enums import UserRole, UserStatus
from app.identity.exceptions import (
    AccountNotActiveError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
)
from app.identity.models import User
from app.identity.repository import UserRepository
from app.identity.schemas import TokenResponse, UserRegisterRequest

# Pre-computed dummy Argon2id hash used to mitigate timing side-channel attacks for non-existent users
_DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$P2T85e50pXJ1Mh+7K44j07Q/Gv3yqV1T0c1pX9pA2sY"


class IdentityService:
    """Coordinates user onboarding, credential verification, and access tokens."""

    def __init__(
        self,
        session: AsyncSession,
        user_repo: UserRepository | None = None,
    ) -> None:
        self.session = session
        self.user_repo = user_repo or UserRepository(session)

    async def register_customer(self, data: UserRegisterRequest) -> User:
        """Register a new customer account.

        Guarantees:
        - Only CUSTOMER role is assigned; public clients cannot request privileged roles.
        - Passwords are validated and hashed with Argon2id before database persistence.
        - Normalized email is checked prior to insert, and duplicate race conditions
          are caught via database unique constraint handling.
        """
        normalized_email = data.email.strip().lower()

        # Check existing user
        existing_user = await self.user_repo.get_by_email(normalized_email)
        if existing_user is not None:
            raise UserAlreadyExistsError("A user with this email already exists.")

        # Hash password securely
        password_hash = hash_password(data.password)

        new_user = User(
            email=normalized_email,
            password_hash=password_hash,
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            phone=data.phone.strip() if data.phone else None,
            role=UserRole.CUSTOMER,  # Enforce CUSTOMER role strictly
            status=UserStatus.ACTIVE,
        )

        try:
            return await self.user_repo.create(new_user)
        except IntegrityError as exc:
            # Race condition: concurrent registration with identical email
            await self.session.rollback()
            raise UserAlreadyExistsError(
                "A user with this email already exists."
            ) from exc

    async def authenticate_user(self, email: str, password: str) -> User:
        """Authenticate user credentials.

        Guarantees:
        - Constant-work timing protection even when email does not exist.
        - Generic error response to prevent user enumeration.
        - Prevents INACTIVE or SUSPENDED users from authenticating.
        """
        normalized_email = email.strip().lower()
        user = await self.user_repo.get_by_email(normalized_email)

        if user is None:
            # Perform dummy verification to mitigate username enumeration via timing attacks
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentialsError("Invalid email or password.")

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError("Invalid email or password.")

        if user.status != UserStatus.ACTIVE:
            status_val = (
                user.status.value
                if isinstance(user.status, UserStatus)
                else str(user.status)
            )
            raise AccountNotActiveError(
                f"Account is {status_val.lower()}.",
                status=status_val,
            )

        return user

    def create_token_for_user(self, user: User) -> TokenResponse:
        """Generate a signed JWT access token for an authenticated user."""
        access_token = create_access_token(
            subject=user.id,
            extra_claims={
                "email": user.email,
                "role": (
                    user.role.value
                    if isinstance(user.role, UserRole)
                    else str(user.role)
                ),
            },
        )
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
        )
