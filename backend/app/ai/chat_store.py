"""
AI 聊天对话历史存储（MongoDB）

与传统后端完全独立：自己的连接、自己的库（默认 meiwei_ai）。
MongoDB 是项目的必需依赖（地位与 MySQL 相同）：启动时强校验连通性，
运行期读写失败直接抛错，没有降级选项。
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List

from app.ai import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_client = None
_index_ready = False


def _get_collection():
    """惰性创建 MongoClient（模块导入时不连接；连通性由启动时的 check_connection 保证）。"""
    global _client, _index_ready
    if _client is None:
        from pymongo import MongoClient

        _client = MongoClient(config.MONGODB_URL, serverSelectionTimeoutMS=2000)
    col = _client[config.MONGODB_DB]["chat_messages"]
    if not _index_ready:
        col.create_index([("user_id", 1), ("created_at", -1)])
        _index_ready = True
        logger.info(f"[ChatStore] MongoDB 已连接: {config.MONGODB_URL}/{config.MONGODB_DB}")
    return col


def _load_history_sync(user_id: int, limit: int) -> List[Dict[str, Any]]:
    col = _get_collection()
    cursor = (
        col.find({"user_id": user_id}, {"_id": 0, "role": 1, "content": 1})
        .sort("created_at", -1)
        .limit(limit)
    )
    # 取出后是倒序，翻转为正序
    return list(reversed(list(cursor)))


def _append_history_sync(user_id: int, entries: List[Dict[str, str]]) -> None:
    col = _get_collection()
    now = datetime.utcnow()
    docs = [
        {"user_id": user_id, "role": e["role"], "content": e["content"], "created_at": now}
        for e in entries
        if e.get("content")
    ]
    if docs:
        col.insert_many(docs)


def _clear_history_sync(user_id: int) -> int:
    return _get_collection().delete_many({"user_id": user_id}).deleted_count


async def check_connection() -> None:
    """启动时校验 MongoDB 连通性并确保索引就绪（失败则应用无法启动）。"""
    await asyncio.to_thread(_get_collection)


async def load_history(user_id: int, limit: int | None = None) -> List[Dict[str, Any]]:
    """读取用户最近的对话历史（正序）。每个用户只读取自己的记录。"""
    return await asyncio.to_thread(
        _load_history_sync, user_id, limit or config.CHAT_HISTORY_LIMIT
    )


async def append_history(user_id: int, entries: List[Dict[str, str]]) -> None:
    """追加对话记录（按 user_id 隔离）。"""
    await asyncio.to_thread(_append_history_sync, user_id, entries)


async def clear_history(user_id: int) -> int:
    """清空指定用户的全部聊天记录，返回删除条数。"""
    deleted = await asyncio.to_thread(_clear_history_sync, user_id)
    logger.info(f"[ChatStore] 已清空用户 {user_id} 的聊天记录，共 {deleted} 条")
    return deleted
