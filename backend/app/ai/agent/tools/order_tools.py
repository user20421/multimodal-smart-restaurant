"""
订单工具

查询能力尽量复用传统后端（order_repo / order_service），
按时间范围过滤等后端没有的能力在本模块内新增（只调用、不修改传统代码）。
"""
from datetime import datetime, timedelta, timezone
from typing import List

from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.agent.context import AgentContext
from app.ai.agent.tools.cart_tools import cart_clear, write_refusal_text
from app.core.database import AsyncSessionLocal
from app.core.exceptions import AppException
from app.core.logging_config import get_logger
from app.models.order import Order
from app.repositories.order_repo import order_repo
from app.schemas.order import CartItem
from app.services import order_service
from app.utils.formatters import LOCAL_TIME_OFFSET, fmt_price, order_status_text, utc_to_local

logger = get_logger(__name__)

# 单次查询最多拉取的订单数（时间范围过滤在这个集合内做）
_MAX_FETCH = 100

# 下单类动作词（必须出现在用户当前这句话中，place_order 才允许执行）
_ORDER_WORDS = ("下单", "结算", "买单", "付款", "交钱")


def _format_orders(orders: List[Order], empty_text: str) -> str:
    if not orders:
        return empty_text
    lines = []
    for o in orders:
        local_time = utc_to_local(o.created_at)
        time_text = local_time.strftime("%m月%d日 %H:%M") if local_time else "未知时间"
        items_text = "、".join(
            f"{oi.menu_item.name if oi.menu_item else '未知菜品'} ×{oi.quantity}"
            for oi in o.items
        )
        # 两行排版：第一行订单号/状态/时间，第二行缩进列菜品明细，长列表更易读
        lines.append(
            f"- **订单 [{o.id}]**（{order_status_text(o.status)}）{time_text}\n"
            f"  {items_text}，共 ¥{fmt_price(o.total_price)}"
        )
    return "\n".join(lines)


async def query_recent_orders(db: AsyncSession, user_id: int, n: int = 5) -> str:
    """最近 n 条订单（复用 order_repo.get_by_user，按时间倒序）。"""
    n = max(1, min(n, 20))
    orders = await order_repo.get_by_user(db, user_id, limit=n)
    return _format_orders(orders, "您最近还没有订单记录。")


async def query_orders_last_days(db: AsyncSession, user_id: int, days: int) -> str:
    """最近 n 天的订单（ai 侧新增能力：取回后按 UTC 朴素时间过滤）。"""
    days = max(1, min(days, 30))
    threshold_utc = datetime.utcnow() - timedelta(days=days)
    orders = await order_repo.get_by_user(db, user_id, limit=_MAX_FETCH)
    filtered = [o for o in orders if o.created_at and o.created_at >= threshold_utc]
    return _format_orders(filtered, f"最近 {days} 天您没有订单记录。")


async def query_orders_on_date(db: AsyncSession, user_id: int, days_ago: int) -> str:
    """某个本地自然日的订单：days_ago=0 今天、1 昨天、2 前天（最大 30）。

    与 query_orders_last_days（范围包含今天）不同，本函数严格限定单日，
    保证“问昨天绝不带出今天的订单”。
    """
    days_ago = max(0, min(days_ago, 30))
    now_local = datetime.now(timezone(LOCAL_TIME_OFFSET))
    day_start_local = (now_local - timedelta(days=days_ago)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # 数据库存 UTC 朴素时间：本地自然日边界换算为 UTC
    start_utc = day_start_local.replace(tzinfo=None) - LOCAL_TIME_OFFSET
    end_utc = start_utc + timedelta(days=1)
    orders = await order_repo.get_by_user(db, user_id, limit=_MAX_FETCH)
    filtered = [o for o in orders if o.created_at and start_utc <= o.created_at < end_utc]
    day_label = day_start_local.strftime("%m月%d日")
    prefix = {0: "今天", 1: "昨天", 2: "前天"}.get(days_ago, f"{days_ago} 天前")
    return _format_orders(filtered, f"{prefix}（{day_label}）您没有订单记录。")


async def query_today_orders(db: AsyncSession, user_id: int) -> str:
    """今天（本地自然日）的订单。"""
    now_local = datetime.now(timezone(LOCAL_TIME_OFFSET))
    today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    # 数据库存 UTC 朴素时间：本地今日 00:00 换算为 UTC 边界
    utc_start = today_start_local.replace(tzinfo=None) - LOCAL_TIME_OFFSET
    orders = await order_repo.get_by_user(db, user_id, limit=_MAX_FETCH)
    filtered = [o for o in orders if o.created_at and o.created_at >= utc_start]
    return _format_orders(filtered, "今天您还没有下单。")


async def place_order_from_cart(
    ctx: AgentContext, remark: str | None = None, db: AsyncSession | None = None
) -> str:
    """用当前购物车快照下单。成功则清空购物车快照；失败原样保留。

    db 缺省时使用独立会话（工具可能被并行调用，共享请求会话会冲突）。
    """
    if not ctx.cart:
        return "购物车是空的，无法下单。请先挑选菜品。"
    try:
        items = [
            CartItem(
                menu_item_id=int(e["menu_item_id"]),
                name=str(e["name"]),
                quantity=int(e["quantity"]),
                unit_price=float(e["unit_price"]),
            )
            for e in ctx.cart
        ]
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"[OrderTools] 购物车快照数据异常: {e}")
        return "购物车数据异常，请在购物车页面确认后再下单。"

    session = db
    own_session = None
    if session is None:
        own_session = AsyncSessionLocal()
        session = own_session
    try:
        order = await order_service.create_order(session, ctx.user_id, items, remark)
    except AppException as e:
        return f"下单失败：{e.message}。购物车内容未变化。"
    except Exception as e:
        logger.exception(f"[OrderTools] 下单异常: {e}")
        return "下单失败：服务暂时异常，请稍后重试。购物车内容未变化。"
    finally:
        if own_session is not None:
            await own_session.close()

    cart_clear(ctx)
    items_text = "、".join(f"{i.name} ×{i.quantity}" for i in order.items)
    return (
        f"下单成功！订单号 [{order.id}]：{items_text}，"
        f"合计 ¥{fmt_price(order.total_price)}。购物车已清空。"
    )


# ============================================================
# LangChain 工具（LLM 调用）
# ============================================================


def build_place_order_tool(ctx: AgentContext) -> list:
    """下单工具（归购物车专员：下单是"购物车 -> 订单"的写操作）。"""

    @tool("place_order")
    async def place_order(remark: str = "") -> str:
        """用当前购物车的内容创建订单（下单）。
        仅当用户明确表达下单/结算意图时调用；remark 为用户备注（可选）。
        注意：用户当前这句话必须包含“下单/结算/买单”等明确动作词，否则工具会拒绝执行。
        """
        if not any(w in (ctx.message or "") for w in _ORDER_WORDS):
            return write_refusal_text("确认下单")
        return await place_order_from_cart(ctx, remark or None)

    return [place_order]


def build_order_tools(ctx: AgentContext) -> list:
    """订单查询工具（只读：查询已下单的进行中/已完成订单）。"""

    @tool("list_recent_orders")
    async def list_recent_orders(n: int = 5) -> str:
        """查询当前用户最近 n 条订单（默认 5 条）。"""
        async with AsyncSessionLocal() as db:
            return await query_recent_orders(db, ctx.user_id, n)

    @tool("list_orders_last_days")
    async def list_orders_last_days(days: int = 2) -> str:
        """查询当前用户最近 n 天内的订单（如"最近两天的订单"）。注意：范围包含今天。"""
        async with AsyncSessionLocal() as db:
            return await query_orders_last_days(db, ctx.user_id, days)

    @tool("list_orders_on_date")
    async def list_orders_on_date(days_ago: int) -> str:
        """查询具体某一天（本地自然日）的订单：days_ago=0 今天、1 昨天、2 前天。
        当用户询问"昨天/前天/今天"等具体某一天时使用，结果只含当天订单。
        """
        async with AsyncSessionLocal() as db:
            return await query_orders_on_date(db, ctx.user_id, days_ago)

    return [list_recent_orders, list_orders_last_days, list_orders_on_date]
