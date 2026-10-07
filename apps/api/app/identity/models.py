"""SQLAlchemy 2.x declarative domain models for the identity domain."""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base
from app.identity.enums import UserRole, UserStatus


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class User(Base):
    """User entity representing authenticated platform accounts."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    phone: Mapped[str | None] = mapped_column(
        sa.String(30),
        nullable=True,
    )
    password_hash: Mapped[str] = mapped_column(
        sa.String(255),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
    )
    last_name: Mapped[str] = mapped_column(
        sa.String(100),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, name="user_role", native_enum=True),
        nullable=False,
        default=UserRole.CUSTOMER,
    )
    status: Mapped[UserStatus] = mapped_column(
        sa.Enum(UserStatus, name="user_status", native_enum=True),
        nullable=False,
        default=UserStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=utc_now,
        server_default=sa.func.now(),
        onupdate=utc_now,
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.Index("ix_users_role", "role"),
        sa.Index("ix_users_status", "status"),
    )

    def __init__(
        self,
        *,
        email: str,
        password_hash: str,
        first_name: str,
        last_name: str,
        id: uuid.UUID | None = None,
        phone: str | None = None,
        role: UserRole = UserRole.CUSTOMER,
        status: UserStatus = UserStatus.ACTIVE,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.id = id if id is not None else uuid.uuid4()
        self.email = email
        self.password_hash = password_hash
        self.first_name = first_name
        self.last_name = last_name
        self.phone = phone
        self.role = role
        self.status = status
        self.created_at = created_at if created_at is not None else utc_now()
        self.updated_at = updated_at if updated_at is not None else utc_now()

    @validates("email")
    def validate_email(self, key: str, address: str) -> str:
        """Normalize email by trimming and lowercasing."""
        if not address or not isinstance(address, str):
            raise ValueError("Email must be a non-empty string.")
        normalized = address.strip().lower()
        if not normalized:
            raise ValueError("Email cannot be blank.")
        return normalized

    def __repr__(self) -> str:
        """Safe string representation omitting password_hash."""
        role_val = self.role.value if isinstance(self.role, UserRole) else self.role
        status_val = (
            self.status.value if isinstance(self.status, UserStatus) else self.status
        )
        return (
            f"<User id={self.id} email={self.email} "
            f"role={role_val} status={status_val}>"
        )
