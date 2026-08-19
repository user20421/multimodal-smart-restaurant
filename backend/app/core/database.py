"""
MySQL 数据库连接管理
使用 SQLAlchemy 2.0 async 模式

数据库表结构与初始数据由项目根目录 init.sql 提供，本模块不负责建库建表。
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.core.config import settings

# 异步引擎
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# ORM 基类
Base = declarative_base()


async def check_mysql() -> None:
    """MySQL 连通性强校验（应用启动时调用）。

    连不上、库不存在或表结构缺失（未执行 init.sql）都会抛异常，拒绝启动。
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT COUNT(*) FROM users"))


async def get_db():
    """FastAPI 依赖注入用"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
