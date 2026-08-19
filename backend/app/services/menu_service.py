"""
菜单服务
"""
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.repositories.menu_repo import menu_category_repo, menu_item_repo
from app.schemas.menu import MenuItemCreate, MenuItemUpdate, MenuItemOut
from app.core.logging_config import get_logger

logger = get_logger(__name__)


async def count_menu_items(db: AsyncSession) -> int:
    """获取菜品总数"""
    return await menu_item_repo.count(db)


async def get_menu_items(db: AsyncSession) -> List[MenuItemOut]:
    """获取所有菜品"""
    items = await menu_item_repo.get_all(db, limit=200)
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
