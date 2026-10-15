"""Comprehensive tests for authentication, password hashing, JWT tokens, and RBAC authorization."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

import app.cart.models
import app.catalog.models
import app.delivery.models
import app.orders.models
import app.payments.models
import app.restaurants.models
from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    decode_access_token,
    hash_password,
    validate_password_length,
    verify_password,
)
from app.identity.dependencies import (
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
    InvalidCredentialsError,
    UserAlreadyExistsError,
)
from app.identity.models import User
from app.identity.repository import UserRepository
from app.identity.schemas import UserRegisterRequest
from app.identity.service import IdentityService
from app.main import app

client = TestClient(app)

# ==============================================================================
# 1. PASSWORD SECURITY & ARGON2ID TESTS
# ==============================================================================


def test_password_hashing_and_verification():
    """Verify that passwords are securely hashed using Argon2id and verified."""
    password = "SuperSecretPassword123!"
    hashed = hash_password(password)

    # Must be Argon2id format
    assert hashed.startswith("$argon2id$")
    assert hashed != password

    # Correct verification
    assert verify_password(password, hashed) is True

    # Incorrect password
    assert verify_password("WrongPassword123!", hashed) is False


def test_password_verification_safe_on_invalid_input():
    """Verify password verification safely returns False on malformed or invalid hashes."""
    assert verify_password("password", "invalid_hash_string") is False
    assert verify_password("password", "") is False
    assert verify_password("", "$argon2id$somehash") is False
    assert verify_password(None, "$argon2id$somehash") is False  # type: ignore[arg-type]
    assert verify_password("password", None) is False  # type: ignore[arg-type]


def test_password_length_validation():
    """Verify password length boundaries (8 to 128 characters)."""
    # Valid
    validate_password_length("12345678")
    validate_password_length("a" * 128)

    # Too short (< 8)
    with pytest.raises(ValueError, match="at least 8 characters"):
        validate_password_length("short")

    # Too long (> 128)
    with pytest.raises(ValueError, match="not exceed 128 characters"):
        validate_password_length("a" * 129)

    # Non-string
    with pytest.raises(TypeError, match="must be a string"):
        validate_password_length(12345678)  # type: ignore[arg-type]


# ==============================================================================
# 2. JWT TOKEN SECURITY & CLAIMS TESTS
# ==============================================================================


def test_create_and_decode_access_token():
    """Verify access token generation with subject and standard claims."""
    user_id = uuid.uuid4()
    token = create_access_token(
        subject=user_id,
        extra_claims={"email": "test@example.com", "role": "CUSTOMER"},
    )

    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["email"] == "test@example.com"
    assert payload["role"] == "CUSTOMER"
    assert "exp" in payload
    assert "iat" in payload


def test_token_expiration_rejection():
    """Verify that expired tokens are detected and raise TokenExpiredError."""
    user_id = uuid.uuid4()
    # Create token that expired 10 minutes ago
    expired_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(minutes=-10),
    )

    with pytest.raises(TokenExpiredError, match="expired"):
        decode_access_token(expired_token)


def test_token_invalid_signature_rejection():
    """Verify that tokens signed with a different key are rejected."""
    user_id = uuid.uuid4()
    tampered_token = jwt.encode(
        {
            "sub": str(user_id),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
            "iat": datetime.now(UTC),
        },
        "completely-different-wrong-secret-key-123456",
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered_token)


def test_token_rejects_none_algorithm():
    """Verify that algorithm substitution attacks ('none') are rejected."""
    payload = {
        "sub": str(uuid.uuid4()),
        "exp": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
        "iat": int(datetime.now(UTC).timestamp()),
    }
    unsigned_token = jwt.encode(payload, key="", algorithm="none")

    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned_token)


def test_token_missing_required_claims():
    """Verify that tokens missing standard claims (sub, exp) are rejected."""
    now = datetime.now(UTC)
    # Missing sub claim
    bad_token = jwt.encode(
        {
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "iat": int(now.timestamp()),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(bad_token)


def test_token_empty_or_malformed_string():
    """Verify that empty or malformed token strings raise InvalidTokenError."""
    with pytest.raises(InvalidTokenError):
        decode_access_token("")

    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.valid.jwt.token")


def test_production_jwt_secret_validation():
    """Verify settings validation requires strong secret in production."""
    settings.validate_production_jwt_secret()  # Should not raise in development

    weak_settings = settings.model_copy(
        update={"API_ENV": "production", "JWT_SECRET": "short"}
    )
    with pytest.raises(ValueError, match="at least 32 characters"):
        weak_settings.validate_production_jwt_secret()


# ==============================================================================
# 3. REGISTRATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_service_register_customer_success():
    """Verify registration creates a user with CUSTOMER role and hashed password."""
    mock_session = AsyncMock()
    mock_user_repo = MagicMock(spec=UserRepository)
    mock_user_repo.get_by_email = AsyncMock(return_value=None)

    async def mock_create(user: User):
        return user

    mock_user_repo.create = AsyncMock(side_effect=mock_create)

    service = IdentityService(mock_session, user_repo=mock_user_repo)
    data = UserRegisterRequest(
        email="  CUSTOMER@EXAMPLE.COM  ",
        password="ValidPassword123!",
        first_name="  John  ",
        last_name="  Doe  ",
        phone="+919876543210",
    )

    user = await service.register_customer(data)

    assert user.email == "customer@example.com"
    assert user.first_name == "John"
    assert user.last_name == "Doe"
    assert user.role == UserRole.CUSTOMER
    assert user.status == UserStatus.ACTIVE
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password("ValidPassword123!", user.password_hash) is True


@pytest.mark.asyncio
async def test_service_register_duplicate_email():
    """Verify registration rejects duplicate email addresses."""
    mock_session = AsyncMock()
    mock_user_repo = MagicMock(spec=UserRepository)
    existing_user = User(
        email="existing@example.com",
        password_hash="hashed",
        first_name="Old",
        last_name="User",
    )
    mock_user_repo.get_by_email = AsyncMock(return_value=existing_user)

    service = IdentityService(mock_session, user_repo=mock_user_repo)
    data = UserRegisterRequest(
        email="existing@example.com",
        password="ValidPassword123!",
        first_name="John",
        last_name="Doe",
    )

    with pytest.raises(UserAlreadyExistsError):
        await service.register_customer(data)


@pytest.mark.asyncio
async def test_service_register_race_condition_integrity_error():
    """Verify concurrent registration collision handling via database IntegrityError."""
    mock_session = AsyncMock()
    mock_user_repo = MagicMock(spec=UserRepository)
    mock_user_repo.get_by_email = AsyncMock(return_value=None)
    mock_user_repo.create = AsyncMock(
        side_effect=IntegrityError("uq_users_email", {}, Exception())
    )

    service = IdentityService(mock_session, user_repo=mock_user_repo)
    data = UserRegisterRequest(
        email="race@example.com",
        password="ValidPassword123!",
        first_name="Race",
        last_name="Condition",
    )

    with pytest.raises(UserAlreadyExistsError):
        await service.register_customer(data)
    mock_session.rollback.assert_awaited()


def test_api_register_endpoint_success():
    """Test POST /api/v1/auth/register creates customer and returns safe UserResponse."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)
    mock_repo.get_by_email = AsyncMock(return_value=None)

    created_id = uuid.uuid4()

    async def mock_create(u: User):
        u.id = created_id
        return u

    mock_repo.create = AsyncMock(side_effect=mock_create)

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        # Patch UserRepository in IdentityService
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "app.identity.service.UserRepository",
                lambda s: mock_repo,
            )
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "testuser@example.com",
                    "password": "StrongPassword123!",
                    "first_name": "Test",
                    "last_name": "User",
                    "role": "ADMIN",  # Privileged role attempt should be ignored
                },
            )

        assert response.status_code == status.HTTP_201_CREATED
        body = response.json()
        assert body["id"] == str(created_id)
        assert body["email"] == "testuser@example.com"
        assert body["role"] == "CUSTOMER"  # Confirms ADMIN was ignored
        assert body["status"] == "ACTIVE"
        assert "password" not in body
        assert "password_hash" not in body
    finally:
        app.dependency_overrides.clear()


def test_api_register_duplicate_returns_409():
    """Test POST /api/v1/auth/register returns 409 Conflict for existing email."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)
    mock_repo.get_by_email = AsyncMock(
        return_value=User(
            email="duplicate@example.com",
            password_hash="hash",
            first_name="A",
            last_name="B",
        )
    )

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.identity.service.UserRepository", lambda s: mock_repo)
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "duplicate@example.com",
                    "password": "StrongPassword123!",
                    "first_name": "Test",
                    "last_name": "User",
                },
            )
        assert response.status_code == status.HTTP_409_CONFLICT
    finally:
        app.dependency_overrides.clear()


def test_api_register_invalid_inputs():
    """Test POST /api/v1/auth/register validates invalid emails, short passwords, blank names."""
    # Short password
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "123",
            "first_name": "Test",
            "last_name": "User",
        },
    )
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Invalid email
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "ValidPassword123!",
            "first_name": "Test",
            "last_name": "User",
        },
    )
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Blank first name
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "ValidPassword123!",
            "first_name": "   ",
            "last_name": "User",
        },
    )
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# ==============================================================================
# 4. LOGIN & AUTHENTICATION TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_service_authenticate_user_success():
    """Verify login authentication with valid credentials returns user."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)

    pwd = "ValidPassword123!"
    hashed = hash_password(pwd)
    mock_user = User(
        email="active@example.com",
        password_hash=hashed,
        first_name="Active",
        last_name="User",
        role=UserRole.CUSTOMER,
        status=UserStatus.ACTIVE,
    )
    mock_repo.get_by_email = AsyncMock(return_value=mock_user)

    service = IdentityService(mock_session, user_repo=mock_repo)
    user = await service.authenticate_user("active@example.com", pwd)
    assert user == mock_user

    # Token creation
    token_resp = service.create_token_for_user(user)
    assert token_resp.token_type == "bearer"
    assert token_resp.access_token is not None
    assert token_resp.expires_in == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


@pytest.mark.asyncio
async def test_service_authenticate_incorrect_password():
    """Verify generic error when password does not match."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)

    hashed = hash_password("CorrectPassword123!")
    mock_user = User(
        email="test@example.com",
        password_hash=hashed,
        first_name="Test",
        last_name="User",
    )
    mock_repo.get_by_email = AsyncMock(return_value=mock_user)

    service = IdentityService(mock_session, user_repo=mock_repo)
    with pytest.raises(InvalidCredentialsError, match="Invalid email or password"):
        await service.authenticate_user("test@example.com", "WrongPassword123!")


@pytest.mark.asyncio
async def test_service_authenticate_non_existent_email():
    """Verify generic error when email is not found, preventing user enumeration."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)
    mock_repo.get_by_email = AsyncMock(return_value=None)

    service = IdentityService(mock_session, user_repo=mock_repo)
    with pytest.raises(InvalidCredentialsError, match="Invalid email or password"):
        await service.authenticate_user("unknown@example.com", "AnyPassword123!")


@pytest.mark.asyncio
async def test_service_authenticate_inactive_and_suspended():
    """Verify inactive and suspended users cannot authenticate."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)

    pwd = "ValidPassword123!"
    hashed = hash_password(pwd)

    # Inactive
    inactive_user = User(
        email="inactive@example.com",
        password_hash=hashed,
        first_name="Inactive",
        last_name="User",
        status=UserStatus.INACTIVE,
    )
    mock_repo.get_by_email = AsyncMock(return_value=inactive_user)

    service = IdentityService(mock_session, user_repo=mock_repo)
    with pytest.raises(AccountNotActiveError, match="inactive"):
        await service.authenticate_user("inactive@example.com", pwd)

    # Suspended
    suspended_user = User(
        email="suspended@example.com",
        password_hash=hashed,
        first_name="Suspended",
        last_name="User",
        status=UserStatus.SUSPENDED,
    )
    mock_repo.get_by_email = AsyncMock(return_value=suspended_user)
    with pytest.raises(AccountNotActiveError, match="suspended"):
        await service.authenticate_user("suspended@example.com", pwd)


def test_api_login_success():
    """Test POST /api/v1/auth/login returns access token."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)

    pwd = "Password123!"
    hashed = hash_password(pwd)
    user = User(
        id=uuid.uuid4(),
        email="login@example.com",
        password_hash=hashed,
        first_name="Login",
        last_name="User",
        role=UserRole.CUSTOMER,
        status=UserStatus.ACTIVE,
    )
    mock_repo.get_by_email = AsyncMock(return_value=user)

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.identity.service.UserRepository", lambda s: mock_repo)
            res = client.post(
                "/api/v1/auth/login",
                json={"email": "login@example.com", "password": pwd},
            )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    finally:
        app.dependency_overrides.clear()


def test_api_login_invalid_credentials_returns_401():
    """Test POST /api/v1/auth/login returns 401 with generic error."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)
    mock_repo.get_by_email = AsyncMock(return_value=None)

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.identity.service.UserRepository", lambda s: mock_repo)
            res = client.post(
                "/api/v1/auth/login",
                json={"email": "nonexistent@example.com", "password": "WrongPassword!"},
            )
        assert res.status_code == status.HTTP_401_UNAUTHORIZED
        assert res.json()["detail"] == "Invalid email or password."
        assert "Bearer" in res.headers["WWW-Authenticate"]
    finally:
        app.dependency_overrides.clear()


def test_api_login_suspended_returns_403():
    """Test POST /api/v1/auth/login returns 403 for suspended user."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)

    pwd = "Password123!"
    hashed = hash_password(pwd)
    user = User(
        email="suspended@example.com",
        password_hash=hashed,
        first_name="Suspended",
        last_name="User",
        status=UserStatus.SUSPENDED,
    )
    mock_repo.get_by_email = AsyncMock(return_value=user)

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.identity.service.UserRepository", lambda s: mock_repo)
            res = client.post(
                "/api/v1/auth/login",
                json={"email": "suspended@example.com", "password": pwd},
            )
        assert res.status_code == status.HTTP_403_FORBIDDEN
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# 5. CURRENT USER DEPENDENCY & ROLE-BASED ACCESS CONTROL (RBAC) TESTS
# ==============================================================================


@pytest.mark.asyncio
async def test_get_current_user_valid_token():
    """Verify get_current_user resolves token subject to database User."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="auth@example.com",
        password_hash="hash",
        first_name="Auth",
        last_name="User",
        status=UserStatus.ACTIVE,
    )

    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)
    mock_repo.get_by_id = AsyncMock(return_value=user)

    token = create_access_token(subject=user_id)
    credentials = MagicMock()
    credentials.credentials = token

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.identity.dependencies.UserRepository", lambda s: mock_repo)
        resolved_user = await get_current_user(
            credentials=credentials, session=mock_session
        )

    assert resolved_user == user


@pytest.mark.asyncio
async def test_get_current_user_missing_credentials():
    """Verify get_current_user raises 401 when credentials are None."""
    mock_session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=None, session=mock_session)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "WWW-Authenticate" in exc_info.value.headers


@pytest.mark.asyncio
async def test_get_current_user_user_not_found_in_db():
    """Verify 401 if user is deleted from DB after token issuance."""
    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)
    mock_repo.get_by_id = AsyncMock(return_value=None)

    token = create_access_token(subject=uuid.uuid4())
    credentials = MagicMock()
    credentials.credentials = token

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.identity.dependencies.UserRepository", lambda s: mock_repo)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, session=mock_session)
    assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "no longer exists" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_active_user_rejects_inactive():
    """Verify get_current_active_user raises 403 if user is not ACTIVE."""
    inactive_user = User(
        email="inactive@example.com",
        password_hash="hash",
        first_name="A",
        last_name="B",
        status=UserStatus.INACTIVE,
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_active_user(current_user=inactive_user)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


def test_role_authorization_dependencies():
    """Verify role checks permit matching roles and reject non-matching roles."""
    customer_user = User(
        id=uuid.uuid4(),
        email="cust@example.com",
        password_hash="hash",
        first_name="A",
        last_name="B",
        role=UserRole.CUSTOMER,
        status=UserStatus.ACTIVE,
    )
    admin_user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        password_hash="hash",
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    restaurant_user = User(
        id=uuid.uuid4(),
        email="rest@example.com",
        password_hash="hash",
        first_name="Chef",
        last_name="Owner",
        role=UserRole.RESTAURANT,
        status=UserStatus.ACTIVE,
    )
    delivery_user = User(
        id=uuid.uuid4(),
        email="rider@example.com",
        password_hash="hash",
        first_name="Rider",
        last_name="One",
        role=UserRole.DELIVERY_PARTNER,
        status=UserStatus.ACTIVE,
    )

    # CUSTOMER check
    assert require_customer(customer_user) == customer_user
    with pytest.raises(HTTPException) as exc:
        require_customer(restaurant_user)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    # ADMIN check
    assert require_admin(admin_user) == admin_user
    with pytest.raises(HTTPException) as exc:
        require_admin(customer_user)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    # RESTAURANT check
    assert require_restaurant(restaurant_user) == restaurant_user
    with pytest.raises(HTTPException) as exc:
        require_restaurant(customer_user)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    # DELIVERY_PARTNER check
    assert require_delivery_partner(delivery_user) == delivery_user
    with pytest.raises(HTTPException) as exc:
        require_delivery_partner(customer_user)
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_api_get_me_endpoint_with_auth_token():
    """Test GET /api/v1/auth/me requires valid bearer token and returns UserResponse."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="me@example.com",
        password_hash="hashed_pw",
        first_name="Jane",
        last_name="Doe",
        role=UserRole.CUSTOMER,
        status=UserStatus.ACTIVE,
    )

    mock_session = AsyncMock()
    mock_repo = MagicMock(spec=UserRepository)
    mock_repo.get_by_id = AsyncMock(return_value=user)

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        token = create_access_token(subject=user_id)

        # 1. Unauthenticated request
        res_no_auth = client.get("/api/v1/auth/me")
        assert res_no_auth.status_code == status.HTTP_401_UNAUTHORIZED

        # 2. Authenticated request
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.identity.dependencies.UserRepository", lambda s: mock_repo)
            res = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["id"] == str(user_id)
        assert data["email"] == "me@example.com"
        assert data["role"] == "CUSTOMER"
        assert "password" not in data
        assert "password_hash" not in data
    finally:
        app.dependency_overrides.clear()
