"""
菜品知识同步

从数据库读取真实菜单（调用传统后端 menu_service，只调用不修改），
为每道菜生成一份 Markdown 知识文档到 rag/data/dishes/。

数据库是菜品信息的唯一事实源。本模块由 rag/manager.py 在后端启动时
及菜单变更时自动调用，也可手动执行：
    cd backend
    python -m app.ai.rag.sync_dishes
"""
import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, engine
from app.services import menu_service

DISHES_DIR = Path(__file__).resolve().parent / "data" / "dishes"

SPICY_TEXT = {0: "不辣", 1: "微辣", 2: "中辣", 3: "特辣"}


def _dish_to_markdown(item) -> str:
    """将菜品信息渲染为一份知识文档。

    不含价格与库存：两者是动态数据，一律以 search_dish 实时查询数据库为准，
    避免知识库快照与库内真实值不一致。
    """
    lines = [
        f"# {item.name}",
        "",
        f"- 分类：{item.category}",
        f"- 辣度：{SPICY_TEXT.get(item.spicy_level, '未知')}",
    ]
    if item.tags:
        lines.append(f"- 标签：{item.tags.replace(',', '、')}")
    if item.is_recommended:
        lines.append("- 本店招牌推荐菜")
    lines.append("")
    if item.description:
        lines.append(item.description.strip())
    return "\n".join(lines) + "\n"


async def sync_dishes(db: AsyncSession) -> int:
    """从数据库同步菜品文档（先清空旧文档，保证与库一致），返回菜品数量。"""
    items = await menu_service.get_menu_items(db)

    DISHES_DIR.mkdir(parents=True, exist_ok=True)
    for old in DISHES_DIR.glob("*.md"):
        old.unlink()

    for item in items:
        (DISHES_DIR / f"{item.name}.md").write_text(
            _dish_to_markdown(item), encoding="utf-8"
        )
    return len(items)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        count = await sync_dishes(db)
    await engine.dispose()
    print(f"已同步 {count} 道菜品文档到 {DISHES_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
