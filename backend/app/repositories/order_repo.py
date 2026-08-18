"""
订单数据访问层
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from sqlalchemy.orm import selectinload
from typing import List, Optional

from app.models.order import Order, OrderItem
from app.repositories.base import BaseRepository
from app.utils.formatters import LOCAL_TIME_OFFSET


class OrderRepository(BaseRepository[Order]):
    def __init__(self):
        super().__init__(Order)

    async def get_by_user(self, db: AsyncSession, user_id: int, limit: int = 20, offset: int = 0) -> List[Order]:
        result = await db.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(desc(Order.created_at))
            .offset(offset)
            .limit(limit)
            .options(
                selectinload(Order.items).selectinload(OrderItem.menu_item),
                selectinload(Order.user),
            )
        )
        return result.scalars().all()

    async def count_by_user(self, db: AsyncSession, user_id: int) -> int:
        result = await db.execute(select(func.count(Order.id)).where(Order.user_id == user_id))
        return result.scalar() or 0

    async def get_with_items(self, db: AsyncSession, order_id: int) -> Optional[Order]:
        result = await db.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.items).selectinload(OrderItem.menu_item),
                selectinload(Order.user),
            )
        )
        return result.scalar_one_or_none()

    async def get_all_orders(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Order]:
        result = await db.execute(
            select(Order)
            .order_by(desc(Order.created_at))
            .offset(skip)
            .limit(limit)
            .options(
                selectinload(Order.items).selectinload(OrderItem.menu_item),
                selectinload(Order.user),
            )
        )
        return result.scalars().all()

    async def count_all(self, db: AsyncSession) -> int:
        result = await db.execute(select(func.count(Order.id)))
        return result.scalar() or 0

    async def get_today_orders(self, db: AsyncSession) -> List[Order]:
        """获取今日订单（按本地日期 00:00 起）。
        数据库存储的是 UTC 朴素时间，需将本地今日起点换算为 UTC 边界再比较。
        """
        now = datetime.now(timezone(timedelta(hours=8)))
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # 本地今日 00:00 对应的 UTC 时间 = 本地时间 - 8 小时
        utc_start = today_start.replace(tzinfo=None) - LOCAL_TIME_OFFSET
        result = await db.execute(
            select(Order)
            .where(Order.created_at >= utc_start)
            .options(selectinload(Order.items).selectinload(OrderItem.menu_item))
        )
        return result.scalars().all()

    async def count_pending_orders(self, db: AsyncSession) -> int:
        """获取待处理订单数量。"""
        result = await db.execute(
            select(func.count(Order.id)).where(Order.status != "completed")
        )
        return result.scalar() or 0

    async def get_pending_orders(self, db: AsyncSession, limit: int = 100) -> List[Order]:
        """获取未完成订单（商家待处理）。"""
        result = await db.execute(
            select(Order)
            .where(Order.status != "completed")
            .order_by(desc(Order.created_at))
            .limit(limit)
            .options(
                selectinload(Order.items).selectinload(OrderItem.menu_item),
                selectinload(Order.user),
            )
        )
        return result.scalars().all()

    async def update_status(self, db: AsyncSession, order_id: int, status: str) -> Optional[Order]:
        """更新订单状态"""
        order = await self.get(db, order_id)
        if not order:
            return None
        order.status = status
        await db.flush()
        return order


class OrderItemRepository(BaseRepository[OrderItem]):
    def __init__(self):
        super().__init__(OrderItem)


order_repo = OrderRepository()
order_item_repo = OrderItemRepository()
