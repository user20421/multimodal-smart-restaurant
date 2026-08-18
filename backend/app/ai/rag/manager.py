"""
知识库生命周期管理

- 后端启动时：向量库缺失或菜单指纹变化 -> 同步菜品文档并重建向量库
- 运行期间：后台任务定时比对菜单指纹，商家端修改菜品后自动重建

由于不修改传统后端代码，菜单变更的感知采用"指纹轮询"而非钩子：
定时查询菜单的 (数量, 最大更新时间) 指纹，变化即触发重建。
"""
import asyncio
from pathlib import Path

from sqlalchemy import func, select

from app.ai import config
from app.ai.rag import retriever
from app.ai.rag.loader import VECTORSTORE_DIR, build_vectorstore
from app.ai.rag.sync_dishes import DISHES_DIR, sync_dishes
from app.core.database import AsyncSessionLocal
from app.core.logging_config import get_logger
from app.models.menu import MenuItem

logger = get_logger(__name__)

FINGERPRINT_FILE = VECTORSTORE_DIR / ".fingerprint"
REFRESH_INTERVAL = 300  # 后台检查间隔（秒）

_refresh_task: asyncio.Task | None = None


def _vectorstore_exists() -> bool:
    return VECTORSTORE_DIR.exists() and any(VECTORSTORE_DIR.iterdir())


def _read_fingerprint() -> str:
    try:
        return FINGERPRINT_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_fingerprint(fp: str) -> None:
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
    FINGERPRINT_FILE.write_text(fp, encoding="utf-8")


async def _menu_fingerprint() -> str:
    """菜单指纹：菜品数量 + 最大更新时间。任何增删改都会改变它。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.count(MenuItem.id), func.max(MenuItem.updated_at))
        )
        count, max_updated = result.one()
    return f"{count}:{max_updated}"


async def _rebuild(fp: str) -> None:
    """同步菜品文档（读数据库）并重建向量库（调 embedding API）。

    持写锁执行：重建期间的检索请求会阻塞等待，而不会读到半成品。
    """
    def _sync_and_build() -> None:
        with retriever.REBUILD_LOCK:
            build_vectorstore()
            retriever.reset()

    async with AsyncSessionLocal() as db:
        count = await sync_dishes(db)
    await asyncio.to_thread(_sync_and_build)
    _write_fingerprint(fp)
    logger.info(f"[AI RAG] 知识库已重建：{count} 道菜品 + 静态文档")


async def ensure_ready() -> None:
    """后端启动时调用：必要时重建向量库。任何失败只告警，不影响主服务启动。"""
    if not config.ZHIPU_API_KEY:
        logger.warning("[AI RAG] 未配置 ZHIPU_API_KEY，跳过知识库初始化")
        return
    try:
        fp = await _menu_fingerprint()
        dishes_ready = DISHES_DIR.exists() and any(DISHES_DIR.glob("*.md"))
        if _vectorstore_exists() and dishes_ready and _read_fingerprint() == fp:
            logger.info("[AI RAG] 向量库已是最新，无需重建")
            return
        logger.info("[AI RAG] 向量库缺失或菜单已变更，开始重建...")
        await _rebuild(fp)
    except Exception as e:
        logger.warning(f"[AI RAG] 知识库初始化失败（不影响主服务）: {e}")


async def _refresh_loop() -> None:
    """后台轮询菜单指纹，变化时自动重建向量库。"""
    while True:
        await asyncio.sleep(REFRESH_INTERVAL)
        try:
            if not config.ZHIPU_API_KEY:
                continue
            fp = await _menu_fingerprint()
            if fp != _read_fingerprint():
                logger.info("[AI RAG] 检测到菜单变更，重建知识库...")
                await _rebuild(fp)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"[AI RAG] 后台检查失败: {e}")


def start_background_refresh() -> None:
    """启动后台定时检查任务。"""
    global _refresh_task
    if _refresh_task is None or _refresh_task.done():
        _refresh_task = asyncio.create_task(_refresh_loop())


def stop_background_refresh() -> None:
    """停止后台定时检查任务。"""
    global _refresh_task
    if _refresh_task and not _refresh_task.done():
        _refresh_task.cancel()
    _refresh_task = None
