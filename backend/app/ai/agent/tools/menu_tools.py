"""
菜单检索工具

resolve_dish 为纯函数，供 fastpath 与工具层共用，证据分级：
精确菜名 -> 名称包含（高频品名优先，如 米饭 -> 白米饭）-> tags -> description。
description 为弱证据（宣传语偶然命中），只出候选列表，绝不单独构成唯一命中；
多候选返回歧义列表，交由上层消歧或让位。
"""
from typing import List, Optional, Tuple

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent.context import AgentContext
from app.core.database import AsyncSessionLocal
from app.models.menu import MenuItem
from app.repositories.menu_repo import menu_item_repo

# 辣度等级 -> 展示文本（与数据库 spicy_level 注释一致：0不辣 1微辣 2中辣 3特辣）
_SPICY_TEXT = {0: "不辣", 1: "微辣", 2: "中辣", 3: "特辣"}


async def resolve_dish(
    db: AsyncSession, keyword: str
) -> Tuple[Optional[MenuItem], List[MenuItem]]:
    """按关键词解析菜品（证据分级：精确菜名 > 名称包含 > tags > description）。

    返回 (唯一命中的菜品或 None, 候选列表)。
    - 精确命中 / 名称或 tags 唯一候选 -> (item, [item])
    - 0 命中 -> (None, [])
    - 多候选歧义，或仅 description 弱命中 -> (None, candidates)
    """
    keyword = (keyword or "").strip(" ，。,.!！?？")
    if not keyword:
        return None, []
    item = await menu_item_repo.get_by_name(db, keyword)
    if item:
        return item, [item]
    # 名称包含优先：点菜消歧场景下，名称候选比 tags/描述噪音更贴近用户本意
    name_hits = list(
        (await db.execute(select(MenuItem).where(MenuItem.name.contains(keyword)))).scalars().all()
    )
    if len(name_hits) == 1:
        return name_hits[0], name_hits
    if name_hits:
        return None, name_hits
    # 结构化 tags 为中等证据：唯一可命中，多候选即歧义
    tag_hits = list(
        (await db.execute(select(MenuItem).where(MenuItem.tags.contains(keyword)))).scalars().all()
    )
    if len(tag_hits) == 1:
        return tag_hits[0], tag_hits
    if tag_hits:
        return None, tag_hits
    # description 为弱证据（宣传语偶然命中）：只出候选供上层消歧，不单独构成命中
    desc_hits = list(
        (await db.execute(select(MenuItem).where(MenuItem.description.contains(keyword)))).scalars().all()
    )
    return None, desc_hits


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
            spicy = _SPICY_TEXT.get(item.spicy_level, "未知")
            return f"唯一命中：{_describe(item)}，辣度 {spicy}（固定属性，顾客不可选择或调整）"
        if not candidates:
            return f"菜单中没有找到与“{keyword}”相关的菜品。"
        lines = "\n".join(f"- {_describe(c)}" for c in candidates[:5])
        return f"找到 {len(candidates)} 个候选（存在歧义，请向用户确认）：\n{lines}"

    return [search_dish]
