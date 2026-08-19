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


async def check_redis() -> bool:
    """Redis 连通性软校验（应用启动时调用）：返回是否可用，不抛异常。

    不可用时验证码服务会降级为进程内内存缓存，不影响启动。
    """
    try:
        client = await get_redis()
        await client.ping()
        await client.aclose()
        return True
    except Exception:
        return False
