"""
Agent 工具层单元测试

重点：resolve_dish 歧义分支、下单成功后购物车清空、时间范围过滤。
使用 SQLite 内存数据库。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base
from app.models.user import User
from app.models.menu import MenuItem
from app.models.order import Order, OrderItem
from app.ai.agent.context import AgentContext
from app.ai.agent.tools.menu_tools import resolve_dish
from app.ai.agent.tools.order_tools import (
    place_order_from_cart,
    query_orders_last_days,
    query_orders_on_date,
    query_recent_orders,
    query_today_orders,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="function")
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestSessionLocal() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def sample_data(db: AsyncSession):
    user = User(username="tool_user", password="", role="customer")
    db.add(user)
    db.add(MenuItem(name="宫保鸡丁", price=38.0, category="热菜", stock=10, is_recommended=1))
    db.add(MenuItem(name="夫妻肺片", price=32.0, category="凉菜", stock=10, is_recommended=0))
    db.add(MenuItem(name="麻婆豆腐", price=22.0, category="热菜", stock=10, is_recommended=0))
    db.add(MenuItem(name="担担面", price=18.0, category="主食", stock=10, is_recommended=0))
    await db.commit()
    return {"user": user}


def make_ctx(db: AsyncSession, user_id: int, cart=None) -> AgentContext:
    return AgentContext(db=db, user_id=user_id, cart=list(cart or []))


# ============================================================
# resolve_dish
# ============================================================


async def test_resolve_exact(db, sample_data):
    item, candidates = await resolve_dish(db, "宫保鸡丁")
    assert item is not None and item.name == "宫保鸡丁"


async def test_resolve_fuzzy_unique(db, sample_data):
    """模糊搜索仅一个候选时自动命中"""
    item, _ = await resolve_dish(db, "肺片")
    assert item is not None and item.name == "夫妻肺片"


async def test_resolve_none(db, sample_data):
    item, candidates = await resolve_dish(db, "佛跳墙")
    assert item is None and candidates == []


async def test_resolve_ambiguous(db, sample_data):
    """多个候选（"豆腐"/"面"类模糊词）-> 歧义，不自动挑选"""
    item, candidates = await resolve_dish(db, "热菜")
    # "热菜" 不匹配名称，但此 fixture 中 description/tags 为空，故用更直接的多候选场景
    item2, candidates2 = await resolve_dish(db, "丁")
    # "丁" 只命中宫保鸡丁 -> 唯一
    assert item2 is not None
    # 构造真正歧义：再插一道菜
    db.add(MenuItem(name="宫保虾球", price=58.0, category="海鲜", stock=5, is_recommended=0))
    await db.commit()
    item3, candidates3 = await resolve_dish(db, "宫保")
    assert item3 is None and len(candidates3) == 2


# ============================================================
# 下单
# ============================================================


async def test_place_order_success_clears_cart(db, sample_data):
    cart = [
        {"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0},
        {"menu_item_id": 4, "name": "担担面", "quantity": 1, "unit_price": 18.0},
    ]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await place_order_from_cart(ctx, db=db)
    assert "下单成功" in reply and "¥94" in reply
    assert ctx.cart == []
    assert ctx.dirty

    # 库存由传统后端校验/扣减
    dish = await db.get(MenuItem, 1)
    assert dish.stock == 8


async def test_place_order_insufficient_stock_keeps_cart(db, sample_data):
    """库存不足 -> 下单失败且购物车原样保留（不可错办）"""
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 999, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await place_order_from_cart(ctx, db=db)
    assert "下单失败" in reply and "库存不足" in reply
    assert len(ctx.cart) == 1  # 购物车未被清空

    dish = await db.get(MenuItem, 1)
    assert dish.stock == 10  # 库存未被扣减


async def test_place_order_empty_cart(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await place_order_from_cart(ctx, db=db)
    assert "空的" in reply


# ============================================================
# 订单查询（含时间范围过滤）
# ============================================================


async def _make_order(db: AsyncSession, user_id: int, days_ago: int, total: float) -> Order:
    order = Order(
        user_id=user_id,
        status="confirmed",
        total_price=total,
        created_at=datetime.utcnow() - timedelta(days=days_ago),
    )
    db.add(order)
    await db.flush()
    db.add(OrderItem(order_id=order.id, menu_item_id=1, quantity=1, unit_price=total))
    await db.commit()
    return order


async def test_query_recent_orders(db, sample_data):
    uid = sample_data["user"].id
    await _make_order(db, uid, 0, 38.0)
    await _make_order(db, uid, 1, 22.0)
    await _make_order(db, uid, 5, 18.0)

    text = await query_recent_orders(db, uid, 2)
    assert "¥38" in text and "¥22" in text and "¥18" not in text


async def test_query_orders_last_days(db, sample_data):
    uid = sample_data["user"].id
    await _make_order(db, uid, 1, 38.0)   # 昨天
    await _make_order(db, uid, 10, 22.0)  # 10 天前

    text = await query_orders_last_days(db, uid, 2)
    assert "¥38" in text and "¥22" not in text

    text30 = await query_orders_last_days(db, uid, 30)
    assert "¥22" in text30


async def test_query_today_orders(db, sample_data):
    uid = sample_data["user"].id
    await _make_order(db, uid, 0, 38.0)
    await _make_order(db, uid, 3, 22.0)

    text = await query_today_orders(db, uid)
    assert "¥38" in text and "¥22" not in text


async def test_query_orders_on_date(db, sample_data):
    """具体某一天查询：查昨天只返回昨天的订单，绝不带出今天的"""
    uid = sample_data["user"].id
    await _make_order(db, uid, 0, 38.0)   # 今天
    await _make_order(db, uid, 1, 22.0)   # 昨天
    await _make_order(db, uid, 2, 18.0)   # 前天

    yesterday = await query_orders_on_date(db, uid, 1)
    assert "¥22" in yesterday and "¥38" not in yesterday and "¥18" not in yesterday

    today = await query_orders_on_date(db, uid, 0)
    assert "¥38" in today and "¥22" not in today

    none_day = await query_orders_on_date(db, uid, 5)
    assert "没有订单" in none_day
