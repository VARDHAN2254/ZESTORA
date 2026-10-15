"""Identity domain module for ZESTORA API."""

from app.identity.dependencies import (
    RequireRoles,
    get_current_active_user,
    get_current_user,
    require_admin,
    require_customer,
    require_delivery_partner,
    require_restaurant,
)
from app.identity.enums import UserRole, UserStatus
from app.identity.exceptions import (
    AccountNotActiveError,
    IdentityError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.identity.models import User
from app.identity.repository import UserRepository
from app.identity.router import router as auth_router
from app.identity.schemas import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.identity.service import IdentityService

__all__ = [
    "AccountNotActiveError",
    "IdentityError",
    "IdentityService",
    "InvalidCredentialsError",
    "RequireRoles",
    "TokenResponse",
    "User",
    "UserAlreadyExistsError",
    "UserLoginRequest",
    "UserNotFoundError",
    "UserRegisterRequest",
    "UserRepository",
    "UserResponse",
    "UserRole",
    "UserStatus",
    "auth_router",
    "get_current_active_user",
    "get_current_user",
    "require_admin",
    "require_customer",
    "require_delivery_partner",
    "require_restaurant",
]
