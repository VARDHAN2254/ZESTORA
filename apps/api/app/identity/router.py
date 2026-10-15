"""FastAPI router for authentication and identity endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.identity.dependencies import get_current_active_user
from app.identity.exceptions import (
    AccountNotActiveError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
)
from app.identity.models import User
from app.identity.schemas import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.identity.service import IdentityService

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
)
async def register(
    payload: UserRegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new customer account with Argon2id password hashing."""
    service = IdentityService(session)
    try:
        user = await service.register_customer(payload)
        return UserResponse.model_validate(user)
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and obtain access token",
)
async def login(
    payload: UserLoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate email and password, returning a signed JWT access token."""
    service = IdentityService(session)
    try:
        user = await service.authenticate_user(payload.email, payload.password)
        return service.create_token_for_user(user)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AccountNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user details",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """Return the profile of the currently authenticated active user."""
    return UserResponse.model_validate(current_user)
