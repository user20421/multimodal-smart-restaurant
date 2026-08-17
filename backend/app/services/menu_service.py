"""
菜单服务
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional

from app.repositories.menu_repo import menu_category_repo, menu_item_repo
from app.models.menu import MenuItem
from app.schemas.menu import MenuItemCreate, MenuItemUpdate, MenuItemOut, MenuCategoryOut
from app.core.logging_config import get_logger
from app.core.seed_data import get_menu_items as _load_menu_items, get_menu_categories as _load_menu_categories

logger = get_logger(__name__)


async def init_menu_data(db: AsyncSession):
    """初始化菜单数据"""
    # 初始化分类
    for cat_data in _load_menu_categories():
        existing = await menu_category_repo.get_by_name(db, cat_data["name"])
        if not existing:
            await menu_category_repo.create(db, cat_data)

    # 初始化菜品
    count = 0
    for item_data in _load_menu_items():
        existing = await menu_item_repo.get_by_name(db, item_data["name"])
        if not existing:
            await menu_item_repo.create(db, item_data)
            count += 1

    await db.commit()
    logger.info(f"[Init] 菜单数据初始化完成，新增 {count} 道菜品")


async def get_full_menu(db: AsyncSession) -> dict:
    """获取完整菜单"""
    categories = await menu_category_repo.get_all_ordered(db)
    items = await get_menu_items(db)
    return {
        "categories": [MenuCategoryOut.model_validate(c) for c in categories],
        "items": items,
    }


async def count_menu_items(db: AsyncSession) -> int:
    """获取菜品总数"""
    return await menu_item_repo.count(db)


async def get_menu_items(db: AsyncSession) -> List[MenuItemOut]:
    """获取所有菜品"""
    items = await menu_item_repo.get_all(db, limit=200)
    return [MenuItemOut.model_validate(i) for i in items]


async def get_recommended_items(db: AsyncSession, limit: int = 8) -> List[MenuItemOut]:
    """获取推荐菜品"""
    items = await menu_item_repo.get_recommended(db, limit)
    return [MenuItemOut.model_validate(i) for i in items]


async def search_menu_items(db: AsyncSession, keyword: str) -> List[MenuItemOut]:
    """搜索菜品"""
    items = await menu_item_repo.search_by_keyword(db, keyword)
    return [MenuItemOut.model_validate(i) for i in items]


async def create_menu_item(db: AsyncSession, data: MenuItemCreate) -> MenuItemOut:
    """创建菜品"""
    item = await menu_item_repo.create(db, data.model_dump())
    await db.commit()
    return MenuItemOut.model_validate(item)


async def update_menu_item(db: AsyncSession, item_id: int, data: MenuItemUpdate) -> MenuItemOut:
    """更新菜品"""
    update_data = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    item = await menu_item_repo.update(db, item_id, update_data)
    if not item:
        from app.core.exceptions import NotFoundException
        raise NotFoundException("菜品不存在")
    await db.commit()
    return MenuItemOut.model_validate(item)


async def delete_menu_item(db: AsyncSession, item_id: int) -> bool:
    """删除菜品"""
    result = await menu_item_repo.delete(db, item_id)
    if result:
        await db.commit()
    return result


async def get_top_selling_items(db: AsyncSession, limit: int = 5) -> List[MenuItemOut]:
    """按销量返回热销菜品。"""
    result = await db.execute(select(MenuItem).order_by(MenuItem.sales_count.desc()).limit(limit))
    return [MenuItemOut.model_validate(i) for i in result.scalars().all()]


async def get_item_by_name(db: AsyncSession, name: str) -> Optional[MenuItemOut]:
    """按名称精确或模糊匹配单个菜品。"""
    item = await menu_item_repo.get_by_name(db, name)
    if item:
        return MenuItemOut.model_validate(item)
    # 模糊匹配
    items = await menu_item_repo.search_by_keyword(db, name)
    if items:
        return MenuItemOut.model_validate(items[0])
    return None


async def get_top_selling_dishes(db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
    """查询销量最高的菜品，返回字典列表。"""
    try:
        items = await get_top_selling_items(db, limit)
        return [
            {
                "name": item.name,
                "price": float(item.price),
                "description": item.description or "",
                "tags": item.tags or "",
                "sales_count": item.sales_count or 0,
                "category": item.category,
            }
            for item in items
        ]
    except Exception as e:
        logger.warning(f"[MenuService] 查询热销菜品失败: {e}")
        return []
