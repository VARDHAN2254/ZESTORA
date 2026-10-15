"""FastAPI dependencies for token authentication and role-based authorization."""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenExpiredError, decode_access_token
from app.identity.enums import UserRole, UserStatus
from app.identity.models import User
from app.identity.repository import UserRepository

# Bearer security scheme; auto_error=False allows returning custom 401 with headers
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the Bearer token, resolving the subject to the User record in DB.

    The database is treated as authoritative for user existence, current status, and role.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except TokenExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired.",
            headers={
                "WWW-Authenticate": (
                    'Bearer error="invalid_token", error_description="Token expired"'
                )
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from exc

    subject_str = payload.get("sub")
    if not subject_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = uuid.UUID(subject_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identifier format in token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Database is authoritative
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Ensure the authenticated user account is in ACTIVE status."""
    if current_user.status != UserStatus.ACTIVE:
        status_val = (
            current_user.status.value
            if isinstance(current_user.status, UserStatus)
            else str(current_user.status)
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User account is {status_val.lower()}.",
        )
    return current_user


class RequireRoles:
    """Dependency callable verifying the authenticated active user possesses an authorized role."""

    def __init__(self, *roles: UserRole) -> None:
        self.roles = roles

    def __call__(
        self,
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role not in self.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this resource.",
            )
        return current_user


# Pre-configured role restriction dependencies
require_customer = RequireRoles(UserRole.CUSTOMER)
require_restaurant = RequireRoles(UserRole.RESTAURANT)
require_delivery_partner = RequireRoles(UserRole.DELIVERY_PARTNER)
require_admin = RequireRoles(UserRole.ADMIN)
