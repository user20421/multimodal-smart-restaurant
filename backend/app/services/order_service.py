"""
订单服务
负责订单创建、查询等业务逻辑，并统一控制数据库事务。
"""
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Tuple

from app.repositories.order_repo import order_repo, order_item_repo
from app.repositories.menu_repo import menu_item_repo
from app.schemas.order import OrderOut, CartItem, OrderItemOut
from app.core.exceptions import BusinessException, NotFoundException
from app.core.logging_config import get_logger
from app.models.order import Order
from app.utils.formatters import mask_username

logger = get_logger(__name__)


async def _create_order_in_transaction(db: AsyncSession, user_id: int, items: List[CartItem], remark: str = None) -> Order:
    """
    创建订单的核心实现（不管理事务边界，调用方必须已在事务中）。
    流程：校验库存 -> 创建订单 -> 创建订单项 -> 原子扣减库存 -> 增加销量。
    """
    total_price = 0.0
    order_items_data = []

    # 验证库存并计算总价
    for item in items:
        menu_item = await menu_item_repo.get(db, item.menu_item_id)
        if not menu_item:
            raise NotFoundException(f"菜品不存在: {item.name}")
        if menu_item.stock < item.quantity:
            raise BusinessException(f"'{menu_item.name}' 库存不足，仅剩 {menu_item.stock} 份")

        total_price += menu_item.price * item.quantity
        order_items_data.append({
            "menu_item_id": item.menu_item_id,
            "quantity": item.quantity,
            "unit_price": menu_item.price,
        })

    # 创建订单
    order = await order_repo.create(db, {
        "user_id": user_id,
        "status": "confirmed",
        "total_price": total_price,
        "remark": remark,
    })

    # 创建订单项并扣减库存/增加销量
    for oi_data in order_items_data:
        oi_data["order_id"] = order.id
        await order_item_repo.create(db, oi_data)

        # 原子扣减库存：返回 0 表示库存不足
        affected = await menu_item_repo.update_stock(db, oi_data["menu_item_id"], -oi_data["quantity"])
        if affected == 0:
            raise BusinessException(f"'{menu_item.name}' 库存不足，下单失败")

        await menu_item_repo.increment_sales(db, oi_data["menu_item_id"], oi_data["quantity"])

    return order


async def create_order(db: AsyncSession, user_id: int, items: List[CartItem], remark: str = None) -> OrderOut:
    """
    创建订单。
    整个流程在同一个事务中完成：校验库存 -> 创建订单 -> 创建订单项 -> 原子扣减库存 -> 增加销量。
    如果调用方已经开启了事务，则复用该事务且不自行 commit；否则在本函数内显式 commit。
    """
    if not items:
        raise BusinessException("购物车不能为空")

    reuse_tx = db.in_transaction()
    order = await _create_order_in_transaction(db, user_id, items, remark)
    if not reuse_tx:
        await db.commit()

    # 重新加载带 items 的订单（事务已提交或复用外部事务，均可安全加载关联）
    order = await order_repo.get_with_items(db, order.id)
    return _format_order(order)


def _clamp_pagination(page: int, page_size: int) -> Tuple[int, int]:
    """统一分页参数钳制：page >= 1，1 <= page_size <= 100。"""
    return max(1, page), max(1, min(page_size, 100))


async def get_user_orders_paginated(
    db: AsyncSession, user_id: int, page: int = 1, page_size: int = 10
) -> Tuple[List[OrderOut], int, int, int]:
    """分页获取用户订单，返回 (订单列表, 总数, 钳制后的页码, 钳制后的每页数量)。"""
    page, page_size = _clamp_pagination(page, page_size)
    skip = (page - 1) * page_size
    orders = await order_repo.get_by_user(db, user_id, limit=page_size, offset=skip)
    total = await order_repo.count_by_user(db, user_id)
    return [_format_order(o) for o in orders], total, page, page_size


async def count_user_orders(db: AsyncSession, user_id: int) -> int:
    return await order_repo.count_by_user(db, user_id)


async def get_order_detail(db: AsyncSession, order_id: int) -> Optional[OrderOut]:
    """获取订单详情"""
    order = await order_repo.get_with_items(db, order_id)
    if not order:
        return None
    return _format_order(order)


async def get_all_orders_paginated(
    db: AsyncSession, page: int = 1, page_size: int = 10
) -> Tuple[List[OrderOut], int, int, int]:
    """分页获取所有订单（商家），返回 (订单列表, 总数, 钳制后的页码, 钳制后的每页数量)。"""
    page, page_size = _clamp_pagination(page, page_size)
    skip = (page - 1) * page_size
    orders = await order_repo.get_all_orders(db, skip, page_size)
    total = await order_repo.count_all(db)
    return [_format_order(o) for o in orders], total, page, page_size


async def count_all_orders(db: AsyncSession) -> int:
    return await order_repo.count_all(db)


async def get_dashboard_stats(db: AsyncSession) -> dict:
    """获取商家仪表盘统计数据。"""
    today_orders = await order_repo.get_today_orders(db)
    today_revenue = sum(o.total_price for o in today_orders)
    pending_count = await order_repo.count_pending_orders(db)
    return {
        "today_orders": len(today_orders),
        "today_revenue": today_revenue,
        "pending_orders": pending_count,
    }


async def get_pending_orders(db: AsyncSession, limit: int = 100) -> List[OrderOut]:
    """获取待处理订单（未完成的订单）。"""
    orders = await order_repo.get_pending_orders(db, limit)
    return [_format_order(o) for o in orders]


async def complete_order(db: AsyncSession, order_id: int) -> Optional[OrderOut]:
    """商家完成订单制作：更新订单状态为 completed 并提交事务。"""
    order = await order_repo.update_status(db, order_id, "completed")
    if not order:
        return None

    await db.commit()

    # 重新加载完整订单信息
    order = await order_repo.get_with_items(db, order_id)

    return _format_order(order)


def _format_order(order) -> OrderOut:
    """格式化订单输出"""
    items = []
    for oi in order.items:
        items.append(OrderItemOut(
            id=oi.id,
            menu_item_id=oi.menu_item_id,
            name=oi.menu_item.name if oi.menu_item else "未知菜品",
            quantity=oi.quantity,
            unit_price=oi.unit_price,
            subtotal=oi.quantity * oi.unit_price,
        ))
    # 通过 __dict__ 安全获取已预加载的 user 关联，避免触发异步懒加载
    user = order.__dict__.get("user")
    username = mask_username(user.username) if user else None
    return OrderOut(
        id=order.id,
        user_id=order.user_id,
        username=username,
        status=order.status,
        total_price=order.total_price,
        remark=order.remark,
        items=items,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )
