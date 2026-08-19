"""
商家管理路由
"""
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_admin, require_superadmin
from app.schemas.menu import MenuItemCreate, MenuItemUpdate, MenuItemOut
from app.schemas.order import OrderOut, PaginatedOrdersResponse
from app.services.auth_service import reset_admin_password
from app.ai import quota as chat_quota
from app.ai import chat_store
from app.services.menu_service import (
    get_menu_items, create_menu_item, update_menu_item, delete_menu_item, count_menu_items
)
from app.services.order_service import (
    get_all_orders_paginated,
    count_all_orders,
    get_dashboard_stats,
    get_pending_orders,
    complete_order,
)
from app.utils.pdf_export import build_orders_pdf

router = APIRouter()


@router.post("/admin/reset-root-password")
async def admin_reset_root_password(
    current_user: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超级管理员重置管理员 root 的密码为初始值 123456"""
    await reset_admin_password(db)
    return {"message": "已将管理员 root 的密码重置为初始值 123456，下次登录后需修改密码"}


@router.get("/admin/user-quotas")
async def admin_list_user_quotas(
    current_user: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超级管理员查看全部普通用户的智能聊天剩余次数"""
    return await chat_quota.list_customer_quotas(db)


@router.post("/admin/user-quotas/{user_id}/recharge")
async def admin_recharge_user_quota(
    user_id: int,
    current_user: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超级管理员为普通用户充值 100 次智能聊天次数"""
    new_quota = await chat_quota.recharge_quota(db, user_id)
    return {"message": f"已充值 100 次，当前剩余 {new_quota} 次", "chat_quota": new_quota}


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    current_user: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超级管理员删除普通用户（级联删除其订单与 MongoDB 聊天记录）"""
    username = await chat_quota.delete_customer(db, user_id)
    await chat_store.clear_history(user_id)
    return {"message": f"已删除用户 {username}"}


@router.get("/admin/dashboard")
async def admin_dashboard(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """商家仪表盘统计数据"""
    stats = await get_dashboard_stats(db)
    stats["total_items"] = await count_menu_items(db)
    return stats


@router.get("/admin/menu", response_model=list[MenuItemOut])
async def admin_list_menu(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """商家获取全部菜品"""
    items = await get_menu_items(db)
    return items


@router.post("/admin/menu", response_model=MenuItemOut)
async def admin_create_menu(
    data: MenuItemCreate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """创建菜品"""
    item = await create_menu_item(db, data)
    return item


@router.put("/admin/menu/{item_id}", response_model=MenuItemOut)
async def admin_update_menu(
    item_id: int,
    data: MenuItemUpdate,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """更新菜品"""
    item = await update_menu_item(db, item_id, data)
    return item


@router.delete("/admin/menu/{item_id}")
async def admin_delete_menu(
    item_id: int,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """删除菜品"""
    success = await delete_menu_item(db, item_id)
    if success:
        return {"message": "删除成功"}
    raise HTTPException(status_code=404, detail="菜品不存在")


@router.get("/admin/orders", response_model=PaginatedOrdersResponse)
async def admin_list_orders(
    page: int = 1,
    page_size: int = 10,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """商家获取全部订单（分页）"""
    orders, total, page, page_size = await get_all_orders_paginated(db, page, page_size)
    return {
        "items": orders,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/admin/orders/count")
async def admin_count_orders(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """商家获取订单总数"""
    total = await count_all_orders(db)
    return {"total": total}


@router.get("/admin/orders/pending", response_model=list[OrderOut])
async def admin_list_pending_orders(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """商家获取待处理订单（未完成的订单）"""
    orders = await get_pending_orders(db)
    return orders


@router.post("/admin/orders/{order_id}/complete")
async def admin_complete_order(
    order_id: int,
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """商家完成订单制作"""
    order = await complete_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return {"message": "订单已完成", "order": order}


@router.get("/admin/orders/export")
async def admin_export_orders(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """商家导出全部订单为 PDF"""
    orders, _, _, _ = await get_all_orders_paginated(db, page=1, page_size=1000)
    pdf_bytes = build_orders_pdf(
        [o.model_dump() for o in orders],
        title="商家订单列表",
    )
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=all_orders.pdf"},
    )
