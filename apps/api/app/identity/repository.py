"""Identity repository providing async database operations for users."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import User


class UserRepository:
    """Async repository for querying and persisting User entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Retrieve a user by primary key UUID."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Retrieve a user by normalized email."""
        normalized_email = email.strip().lower()
        result = await self.session.execute(
            select(User).where(User.email == normalized_email)
        )
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        """Add and flush a new user entity."""
        self.session.add(user)
        await self.session.flush()
        return user
