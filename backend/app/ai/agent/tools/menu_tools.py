"""
菜单检索工具

resolve_dish 为纯函数，供 fastpath 与工具层共用：
先精确匹配菜名，再模糊搜索（名称/标签/描述），多候选返回歧义列表。
"""
from typing import List, Optional, Tuple

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent.context import AgentContext
from app.core.database import AsyncSessionLocal
from app.models.menu import MenuItem
from app.repositories.menu_repo import menu_item_repo


async def resolve_dish(
    db: AsyncSession, keyword: str
) -> Tuple[Optional[MenuItem], List[MenuItem]]:
    """按关键词解析菜品。

    返回 (唯一命中的菜品或 None, 候选列表)。
    - 精确命中或模糊搜索仅 1 个候选 -> (item, [item])
    - 0 命中 -> (None, [])
    - 多候选歧义 -> (None, candidates)
    """
    keyword = (keyword or "").strip(" ，。,.!！?？")
    if not keyword:
        return None, []
    item = await menu_item_repo.get_by_name(db, keyword)
    if item:
        return item, [item]
    candidates = list(await menu_item_repo.search_by_keyword(db, keyword))
    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates


def _describe(item: MenuItem) -> str:
    return f"{item.name}（¥{item.price}/份，库存 {item.stock}）"


def build_menu_tools(ctx: AgentContext) -> list:
    @tool("search_dish")
    async def search_dish(keyword: str) -> str:
        """按菜名或关键词搜索本店菜单，返回候选菜品（含价格、库存、辣度）。
        当用户提到的菜名不确定、或需要向用户确认候选时使用。
        """
        # 工具可能被并行调用，共享请求会话会冲突，故每次调用使用独立会话
        async with AsyncSessionLocal() as db:
            item, candidates = await resolve_dish(db, keyword)
        if item is not None:
            return f"唯一命中：{_describe(item)}，辣度 {item.spicy_level}/3"
        if not candidates:
            return f"菜单中没有找到与“{keyword}”相关的菜品。"
        lines = "\n".join(f"- {_describe(c)}" for c in candidates[:5])
        return f"找到 {len(candidates)} 个候选（存在歧义，请向用户确认）：\n{lines}"

    return [search_dish]
