"""
L1 正则快速路单元测试

覆盖：中文数字解析、加/减/换/改数量/清空/查看购物车、下单、订单查询、歧义让位。
使用 SQLite 内存数据库（与 tests/unit/test_order_service.py 同风格）。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base
from app.models.user import User
from app.models.menu import MenuItem
from app.ai.agent.context import AgentContext
from app.ai.agent import fastpath
from app.ai.agent.fastpath import parse_quantity

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
    user = User(username="fast_user", password="", role="customer")
    db.add(user)
    db.add(MenuItem(name="宫保鸡丁", price=38.0, category="热菜", stock=50, is_recommended=1))
    db.add(MenuItem(name="糖醋里脊", price=42.0, category="热菜", stock=50, is_recommended=0))
    db.add(MenuItem(name="米饭", price=2.0, category="主食", stock=100, is_recommended=0))
    await db.commit()
    return {"user": user}


def make_ctx(db: AsyncSession, user_id: int, cart=None) -> AgentContext:
    return AgentContext(db=db, user_id=user_id, cart=list(cart or []))


# ============================================================
# 数量解析（纯函数）
# ============================================================


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1", 1), ("3", 3), ("12", 12),
        ("一", 1), ("两", 2), ("二", 2), ("五", 5), ("十", 10),
        ("十一", 11), ("二十", 20), ("二十三", 23),
        ("零", None), ("abc", None), ("", None),
    ],
)
def test_parse_quantity(text, expected):
    assert parse_quantity(text) == expected


# ============================================================
# 加菜
# ============================================================


async def test_add_dish_with_cn_quantity(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "来三份宫保鸡丁")
    assert reply and "3 份宫保鸡丁" in reply
    assert ctx.dirty
    assert ctx.cart == [
        {"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 3, "unit_price": 38.0}
    ]


async def test_add_dish_default_quantity(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "我要一份米饭")
    assert reply and "米饭" in reply
    assert ctx.cart[0]["quantity"] == 1


async def test_add_dish_accumulates(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 1, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    await fastpath.try_handle(ctx, "再加两份宫保鸡丁")
    assert ctx.cart[0]["quantity"] == 3


async def test_add_unknown_dish_falls_through(db, sample_data):
    """零命中 -> 返回 None 让位给 LLM，且购物车不被污染"""
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "来一份佛跳墙")
    assert reply is None
    assert ctx.cart == []
    assert not ctx.dirty


async def test_unrelated_text_falls_through(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    assert await fastpath.try_handle(ctx, "今天天气怎么样") is None
    assert await fastpath.try_handle(ctx, "宫保鸡丁辣不辣") is None


# ============================================================
# 减菜 / 改数量
# ============================================================


async def test_remove_dish(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "宫保鸡丁不要了")
    assert reply and "移除" in reply
    assert ctx.cart == []


async def test_remove_dish_not_in_cart(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "去掉宫保鸡丁")
    assert reply and "没有宫保鸡丁" in reply
    assert not ctx.dirty


async def test_set_quantity(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 3, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "宫保鸡丁只要一份")
    assert reply and "1 份" in reply
    assert ctx.cart[0]["quantity"] == 1


# ============================================================
# 换菜（复合：先减再加）
# ============================================================


async def test_swap_dish(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "把宫保鸡丁换成糖醋里脊")
    assert reply and "换成 2 份糖醋里脊" in reply
    assert len(ctx.cart) == 1
    assert ctx.cart[0]["name"] == "糖醋里脊" and ctx.cart[0]["quantity"] == 2


async def test_swap_with_explicit_quantity(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "把宫保鸡丁换成三份糖醋里脊")
    assert reply and "3 份糖醋里脊" in reply


async def test_swap_dish_not_in_cart(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "把宫保鸡丁换成糖醋里脊")
    assert reply and "没有宫保鸡丁" in reply
    assert ctx.cart == []


async def test_swap_to_unknown_dish_falls_through(db, sample_data):
    """目标菜不存在 -> 让位，绝不把原菜减掉"""
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "把宫保鸡丁换成佛跳墙")
    assert reply is None
    assert ctx.cart[0]["name"] == "宫保鸡丁"


# ============================================================
# 清空 / 查看 / 下单
# ============================================================


async def test_clear_cart(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 1, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "清空购物车")
    assert reply and "已清空" in reply
    assert ctx.cart == []


async def test_clear_cart_variants_not_executed(db, sample_data):
    """清空口令必须逐字精确：变体表述一律不执行，引导用户说出"清空购物车\""""
    for variant in ("把购物车清空", "帮我清空购物车", "请清空我的购物车", "购物车不要了", "重新点"):
        cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 1, "unit_price": 38.0}]
        ctx = make_ctx(db, sample_data["user"].id, cart)
        reply = await fastpath.try_handle(ctx, variant)
        assert reply and "还没有执行" in reply and "明确说出" in reply, variant
        assert len(ctx.cart) == 1, variant


async def test_view_cart(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "看看购物车")
    assert reply and "宫保鸡丁 ×2" in reply and "¥76" in reply
    assert not ctx.dirty


async def test_place_order_success(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "确认下单")
    assert reply and "下单成功" in reply and "¥76" in reply
    assert ctx.cart == []
    assert ctx.dirty


async def test_place_order_empty_cart(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "下单")
    assert reply and "空的" in reply


# ============================================================
# 订单查询
# ============================================================


async def test_recent_orders_empty(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "查看最近5条订单")
    assert reply and "没有订单" in reply


async def test_my_orders_button_phrases(db, sample_data):
    """快捷按钮来源的“查询我的订单/查询订单”应直接命中 L1，不调 LLM"""
    ctx = make_ctx(db, sample_data["user"].id)
    for text in ("查询我的订单", "查询订单", "查看我的订单", "查一下我的订单", "我的订单"):
        reply = await fastpath.try_handle(ctx, text)
        assert reply is not None and "订单" in reply, text


async def test_last_days_orders_empty(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "最近两天的订单")
    assert reply and "没有订单" in reply


async def test_today_orders_empty(db, sample_data):
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "今天的订单")
    assert reply and "还没有下单" in reply


async def test_recent_orders_after_place(db, sample_data):
    """下单后再查最近订单，应能看到"""
    user_id = sample_data["user"].id
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 1, "unit_price": 38.0}]
    ctx = make_ctx(db, user_id, cart)
    await fastpath.try_handle(ctx, "确认下单")

    ctx2 = make_ctx(db, user_id)
    reply = await fastpath.try_handle(ctx2, "最近1条订单")
    assert reply and "宫保鸡丁 ×1" in reply and "¥38" in reply


async def test_yesterday_orders_excludes_today(db, sample_data):
    """问昨天的订单：今天刚下的单绝不能出现（快速路严格限定单日）"""
    user_id = sample_data["user"].id
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 1, "unit_price": 38.0}]
    ctx = make_ctx(db, user_id, cart)
    await fastpath.try_handle(ctx, "确认下单")

    for question in ("昨天的订单", "昨天有订单吗", "前天订单有哪些"):
        ctx2 = make_ctx(db, user_id)
        reply = await fastpath.try_handle(ctx2, question)
        assert reply and "没有订单" in reply and "宫保鸡丁" not in reply


async def test_order_query_requires_full_match(db, sample_data):
    """订单查询快速路必须整句完全匹配：夹杂其他诉求的句子不得触发，让位给 L2"""
    ctx = make_ctx(db, sample_data["user"].id)
    # 含退款/发票等额外诉求，不是纯查询指令 -> 快速路不得处理
    assert await fastpath.try_handle(ctx, "我昨天的订单能退吗") is None
    assert await fastpath.try_handle(ctx, "最近3天订单能开发票吗") is None
    # 整句就是查询 -> 完全匹配命中
    assert await fastpath.try_handle(ctx, "最近3天的订单") is not None


# ============================================================
# 部分换菜（把其中N份X换成M份Y）
# ============================================================


async def test_partial_swap(db, sample_data):
    """部分换：X 减 N，Y 加 M，剩余数量保留"""
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 5, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "把其中两份宫保鸡丁换成一份糖醋里脊")
    assert reply and "2 份宫保鸡丁换成 1 份糖醋里脊" in reply and "还剩 3 份" in reply
    by_name = {e["name"]: e["quantity"] for e in ctx.cart}
    assert by_name == {"宫保鸡丁": 3, "糖醋里脊": 1}


async def test_partial_swap_without_其中(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 3, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "把两份宫保鸡丁换成一份糖醋里脊")
    assert reply and "还剩 1 份" in reply
    by_name = {e["name"]: e["quantity"] for e in ctx.cart}
    assert by_name == {"宫保鸡丁": 1, "糖醋里脊": 1}


async def test_partial_swap_default_to_qty(db, sample_data):
    """右侧缺省数量 -> 与换出数量相同"""
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 4, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "把其中两份宫保鸡丁换成糖醋里脊")
    assert reply and "2 份糖醋里脊" in reply
    by_name = {e["name"]: e["quantity"] for e in ctx.cart}
    assert by_name == {"宫保鸡丁": 2, "糖醋里脊": 2}


async def test_partial_swap_exact_remaining_zero(db, sample_data):
    """换出数量 = 现有数量 -> 原菜移除"""
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "把两份宫保鸡丁换成一份糖醋里脊")
    assert reply and "还剩" not in reply
    by_name = {e["name"]: e["quantity"] for e in ctx.cart}
    assert by_name == {"糖醋里脊": 1}


async def test_partial_swap_insufficient_no_action(db, sample_data):
    """数量不够 -> 明确告知且不执行（不可错办）"""
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 1, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "把其中两份宫保鸡丁换成一份糖醋里脊")
    assert reply and "只有 1 份" in reply
    by_name = {e["name"]: e["quantity"] for e in ctx.cart}
    assert by_name == {"宫保鸡丁": 1}  # 原样保留


async def test_swap_same_dish_rejected(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "把宫保鸡丁换成宫保鸡丁")
    assert reply and "同一道菜" in reply
    assert not ctx.dirty


async def test_set_quantity_via_改成(db, sample_data):
    cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 3, "unit_price": 38.0}]
    ctx = make_ctx(db, sample_data["user"].id, cart)
    reply = await fastpath.try_handle(ctx, "宫保鸡丁改成1份")
    assert reply and "1 份" in reply
    assert ctx.cart[0]["quantity"] == 1


async def test_dish_name_starting_with_cn_numeral_not_misparsed(db, sample_data):
    """菜名以中文数字开头（如"一品豆腐"）不应被误认为数量前缀"""
    db.add(MenuItem(name="一品豆腐", price=26.0, category="素菜", stock=10, is_recommended=0))
    await db.commit()
    ctx = make_ctx(db, sample_data["user"].id)
    reply = await fastpath.try_handle(ctx, "来两份一品豆腐")
    assert reply and "一品豆腐" in reply
    assert ctx.cart[0]["name"] == "一品豆腐" and ctx.cart[0]["quantity"] == 2
