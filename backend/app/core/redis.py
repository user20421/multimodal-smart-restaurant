"""
Redis 连接管理
提供异步 Redis 客户端实例
"""
import redis.asyncio as redis
from app.core.config import settings


async def get_redis() -> redis.Redis:
    """获取 Redis 异步客户端"""
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
        encoding="utf-8",
    )
