"""
用户数据访问层
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)

    async def get_by_username(self, db: AsyncSession, username: str) -> Optional[User]:
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_users_with_face(self, db: AsyncSession) -> List[User]:
        result = await db.execute(select(User).where(User.face_encoding.isnot(None)))
        return result.scalars().all()


user_repo = UserRepository()
