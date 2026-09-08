"""User persistence."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, utcnow


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_bale_id(self, bale_user_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.bale_user_id == bale_user_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.username == username.lstrip("@"))
        )
        return result.scalars().first()

    async def upsert_from_bale(
        self,
        bale_user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> User:
        user = await self.get_by_bale_id(bale_user_id)
        if user is None:
            user = User(
                bale_user_id=bale_user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            self._session.add(user)
            await self._session.flush()
            return user
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.last_seen_at = utcnow()
        return user

    async def set_private_chat(self, user_id: int, has_private_chat: bool) -> None:
        await self._session.execute(
            update(User).where(User.id == user_id).values(has_private_chat=has_private_chat)
        )

    async def set_admin(self, user_id: int, is_admin: bool) -> None:
        await self._session.execute(
            update(User).where(User.id == user_id).values(is_admin=is_admin)
        )

    async def list_admins(self) -> list[User]:
        result = await self._session.execute(select(User).where(User.is_admin.is_(True)))
        return list(result.scalars().all())

    async def forget(self, user_id: int) -> None:
        """Soft-delete a user's personal data (GDPR-style /forget)."""
        await self._session.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                username=None,
                first_name=None,
                last_name=None,
                is_blocked=True,
                is_forgotten=True,
            )
        )
