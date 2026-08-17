"""
MySQL 数据库连接管理
使用 SQLAlchemy 2.0 async 模式
"""
import asyncio

import pymysql
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def _ensure_database_exists():
    """确保业务数据库存在（不存在则创建）。由 init_db 在应用启动时调用。"""
    url = make_url(settings.database_url)
    db_name = url.database
    if not db_name:
        logger.warning("[Database] DATABASE_URL 未指定数据库名，跳过自动建库")
        return
    try:
        conn = pymysql.connect(
            host=url.host or "localhost",
            port=url.port or 3306,
            user=url.username or "root",
            password=url.password or "",
        )
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[Database] 自动创建数据库失败: {e}")


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


async def init_db():
    """初始化数据库：确保库存在并创建表结构（应用启动时调用）"""
    await asyncio.to_thread(_ensure_database_exists)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("[Database] 数据库表初始化完成")


async def get_db():
    """FastAPI 依赖注入用"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
