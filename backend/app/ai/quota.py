"""
智能聊天次数配额管理（AI 模块）

每个普通用户（customer）初始 30 次发送次数，每次发送扣减 1；
次数为 0 时抛出业务异常，前端弹窗提示联系开发人员。
配额的查看、充值与删除用户由超级管理员在管理端操作（api/v1/admin.py 调用）。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessException, NotFoundException
from app.models.user import User

# 次数耗尽时对用户的提示语
QUOTA_EXCEEDED_MESSAGE = "您的智能聊天次数不足，请联系开发人员"

# 新用户初始次数 / 超管单次充值次数
INITIAL_QUOTA = 30
RECHARGE_AMOUNT = 100


async def consume_quota(db: AsyncSession, user_id: int) -> None:
    """扣减一次聊天次数；次数为 0 时抛出业务异常。"""
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundException("用户不存在")
    if (user.chat_quota or 0) <= 0:
        raise BusinessException(QUOTA_EXCEEDED_MESSAGE)
    user.chat_quota -= 1
    await db.commit()


async def list_customer_quotas(db: AsyncSession) -> list[dict]:
    """列出全部普通用户的剩余聊天次数（超级管理员面板用）。"""
    result = await db.execute(
        select(User).where(User.role == "customer").order_by(User.id)
    )
    return [
        {
            "id": u.id,
            "username": u.username,
            "chat_quota": u.chat_quota,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in result.scalars()
    ]


async def recharge_quota(db: AsyncSession, user_id: int) -> int:
    """为普通用户充值 100 次聊天次数，返回充值后的次数。"""
    user = await db.get(User, user_id)
    if not user or user.role != "customer":
        raise NotFoundException("普通用户不存在")
    user.chat_quota = (user.chat_quota or 0) + RECHARGE_AMOUNT
    await db.commit()
    return user.chat_quota


async def delete_customer(db: AsyncSession, user_id: int) -> str:
    """删除普通用户（ORM 级联删除其订单与订单项），返回用户名。"""
    user = await db.get(User, user_id)
    if not user or user.role != "customer":
        raise NotFoundException("普通用户不存在")
    username = user.username
    await db.delete(user)
    await db.commit()
    return username
