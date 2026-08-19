"""
AI 聊天对话历史存储（MongoDB）

与传统后端完全独立：自己的连接、自己的库（默认 meiwei_ai）。
MongoDB 是项目的必需依赖（地位与 MySQL 相同）：启动时强校验连通性，
运行期读写失败直接抛错，没有降级选项。

滚动摘要：单个用户的原始消息超过 SUMMARY_TRIGGER_COUNT 条时，
后台异步把最旧的 SUMMARY_BATCH_SIZE 条压缩进一段滚动摘要（chat_summaries 集合），
进 prompt 时「摘要 + 最近 N 条原文」一起注入，控制 token 成本。
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List

from app.ai import config
from app.core.logging_config import get_logger

logger = get_logger(__name__)

_client = None
_index_ready = False

# 滚动摘要参数：原文总数超过 20 条时，把最旧的 10 条压缩进摘要
SUMMARY_TRIGGER_COUNT = 20
SUMMARY_BATCH_SIZE = 10

# 摘要任务并发保护（同一用户同一时刻最多一个摘要任务）
_summarizing: set[int] = set()

# 摘要提示词：面向点餐场景定制，保留偏好与未决事项，丢弃寒暄
_SUMMARY_PROMPT = (
    "你是餐厅点餐对话的摘要助手。请把【已有摘要】和【新增对话】合并压缩成一段不超过 300 字的摘要。"
    "必须保留：顾客的口味偏好与忌口、讨论过的菜品及数量、已下单或取消的订单结论、未完成的待确认事项。"
    "直接丢弃：寒暄、客套、与点餐无关的闲聊细节。"
    "只输出摘要正文，纯文本三五句话，不要标题、不要列表、不要解释。"
)


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


def _get_summary_collection():
    """滚动摘要集合：每用户一条 {user_id, summary, updated_at}。"""
    return _client[config.MONGODB_DB]["chat_summaries"]


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
    deleted = _get_collection().delete_many({"user_id": user_id}).deleted_count
    # 摘要与原文同生命周期：清空对话时一并清除
    _get_summary_collection().delete_one({"user_id": user_id})
    return deleted


# ============================================================
# 滚动摘要
# ============================================================


def _count_sync(user_id: int) -> int:
    return _get_collection().count_documents({"user_id": user_id})


def _oldest_docs_sync(user_id: int, limit: int) -> List[Dict[str, Any]]:
    cursor = _get_collection().find({"user_id": user_id}).sort("created_at", 1).limit(limit)
    return list(cursor)


def _get_summary_sync(user_id: int) -> str:
    doc = _get_summary_collection().find_one({"user_id": user_id})
    return (doc or {}).get("summary", "")


def _apply_summary_sync(user_id: int, summary: str, delete_ids: list) -> None:
    """写入新摘要并删除已被压缩的原始消息。"""
    _get_summary_collection().update_one(
        {"user_id": user_id},
        {"$set": {"summary": summary, "updated_at": datetime.utcnow()}},
        upsert=True,
    )
    if delete_ids:
        _get_collection().delete_many({"_id": {"$in": delete_ids}})


async def _run_summary_llm(old_summary: str, oldest: List[Dict[str, Any]]) -> str:
    """调用百炼 flash 生成新摘要（可独立替换实现，测试中可 mock）。"""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.ai.llm.bailian import get_chat_llm

    lines = [f"{d['role']}: {d['content']}" for d in oldest]
    payload = f"【已有摘要】\n{old_summary or '（无）'}\n\n【新增对话】\n" + "\n".join(lines)
    result = await get_chat_llm().ainvoke(
        [SystemMessage(content=_SUMMARY_PROMPT), HumanMessage(content=payload)]
    )
    content = result.content
    if not isinstance(content, str):
        content = "".join(str(p) for p in content)
    return content.strip()


async def _summarize_if_needed(user_id: int) -> None:
    """积压超过阈值时，把最旧的一批消息压缩进滚动摘要。失败只告警，不影响聊天。"""
    _summarizing.add(user_id)
    try:
        count = await asyncio.to_thread(_count_sync, user_id)
        if count <= SUMMARY_TRIGGER_COUNT:
            return
        oldest = await asyncio.to_thread(_oldest_docs_sync, user_id, SUMMARY_BATCH_SIZE)
        if not oldest:
            return
        old_summary = await asyncio.to_thread(_get_summary_sync, user_id)
        new_summary = await _run_summary_llm(old_summary, oldest)
        if not new_summary:
            return
        await asyncio.to_thread(
            _apply_summary_sync, user_id, new_summary, [d["_id"] for d in oldest]
        )
        logger.info(
            f"[ChatStore] 用户 {user_id} 对话摘要已更新，压缩 {len(oldest)} 条旧消息"
        )
    except Exception as e:
        logger.warning(f"[ChatStore] 对话摘要失败（不影响聊天，下轮重试）: {e}")
    finally:
        _summarizing.discard(user_id)


def _schedule_summary(user_id: int) -> None:
    """后台异步触发摘要检查（不阻塞当前回复）。"""
    if user_id in _summarizing:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_summarize_if_needed(user_id))


async def check_connection() -> None:
    """启动时校验 MongoDB 连通性并确保索引就绪（失败则应用无法启动）。"""
    await asyncio.to_thread(_get_collection)


async def load_history(user_id: int, limit: int | None = None) -> List[Dict[str, Any]]:
    """读取用户最近的对话历史（正序）。每个用户只读取自己的记录。

    若存在滚动摘要，以 role="system" 条目置于最前，随历史一起注入 prompt。
    """
    messages = await asyncio.to_thread(
        _load_history_sync, user_id, limit or config.CHAT_HISTORY_LIMIT
    )
    summary = await asyncio.to_thread(_get_summary_sync, user_id)
    if summary:
        return [
            {
                "role": "system",
                "content": f"以下为该顾客较早对话的摘要，仅供参考：{summary}",
            }
        ] + messages
    return messages


async def append_history(user_id: int, entries: List[Dict[str, str]]) -> None:
    """追加对话记录（按 user_id 隔离），随后异步检查是否需要滚动摘要。"""
    await asyncio.to_thread(_append_history_sync, user_id, entries)
    _schedule_summary(user_id)


async def clear_history(user_id: int) -> int:
    """清空指定用户的全部聊天记录，返回删除条数。"""
    deleted = await asyncio.to_thread(_clear_history_sync, user_id)
    logger.info(f"[ChatStore] 已清空用户 {user_id} 的聊天记录，共 {deleted} 条")
    return deleted
