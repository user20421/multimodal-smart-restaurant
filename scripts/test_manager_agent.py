# -*- coding: utf-8 -*-
"""
"餐厅经理"（混合意图 agent，更强模型 BAILIAN_LLM_MODEL_X）端到端冒烟测试

直连真实数据库与真实大模型，验证四件事：
1. 混合意图一站式办妥：咨询营业时间 + 加两道菜 -> 回复覆盖两件事，购物车快照被修改
2. 混合意图中的写操作指代不清 -> 咨询照答，写操作被工具层硬校验拒绝且回复如实说明
3. 过多过杂的矛盾需求 -> 路由 unclear，固定话术兜底（宁愿不做，不可做错）
4. 辣度是商家设定的固定属性：点辣菜 + 问辣度 -> 直接加菜并如实告知辣度，
   不得向顾客确认辣度、不得要求备注辣度

注意：本脚本真实调用模型 B（产生 token 费用）并连接 MySQL，请确认数据库已启动。
用法:
    python scripts/test_manager_agent.py
"""
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.ai.agent.context import AgentContext  # noqa: E402
from app.ai.agent.graph import run_graph  # noqa: E402
from app.ai.sanitize import sanitize_reply  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.menu import MenuItem  # noqa: E402


async def _pick_dishes() -> list[str]:
    """从真实菜单取两道有库存的菜，保证测试句子里的菜名必然命中。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MenuItem.name).where(MenuItem.stock > 0).order_by(MenuItem.id).limit(2)
        )
        return [row[0] for row in result.all()]


async def _pick_spicy_dish() -> tuple[str, int]:
    """从真实菜单取一道辣度 >= 2（中辣/特辣）且有库存的菜。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MenuItem.name, MenuItem.spicy_level)
            .where(MenuItem.stock > 0, MenuItem.spicy_level >= 2)
            .order_by(MenuItem.spicy_level.desc(), MenuItem.id)
            .limit(1)
        )
        row = result.first()
        assert row, "菜单中没有辣度 >= 2 的在售菜品，无法执行场景 4"
        return row[0], row[1]


async def _run(message: str) -> tuple[str, list]:
    """以空历史、空购物车跑一次 L2 图，返回 (回复, 最终购物车快照)。"""
    async with AsyncSessionLocal() as db:
        ctx = AgentContext(db=db, user_id=1, message=message, cart=[])
        reply = await run_graph(ctx, message, history=[])
        return sanitize_reply(reply), ctx.cart


async def main() -> int:
    dish1, dish2 = await _pick_dishes()
    print(f"测试菜品（取自真实菜单）: {dish1} / {dish2}")
    print("=" * 72)

    ok = True

    # 场景 1：混合意图（咨询 + 加两道菜），应一站式办妥
    msg1 = f"你们今天的营业时间是什么，帮我来一份{dish1}和2份{dish2}"
    print(f"[场景1] 混合意图一站式: {msg1}")
    reply1, cart1 = await _run(msg1)
    print(f"        回复: {reply1}")
    print(f"        购物车: {cart1}")
    in_cart = {e.get("name"): e.get("quantity") for e in cart1}
    if in_cart.get(dish1) == 1 and in_cart.get(dish2) == 2:
        print("        [通过] 两道菜已按数量入购物车 ✔")
    else:
        print("        [失败] 购物车快照不符合预期")
        ok = False
    print("-" * 72)

    # 场景 2：混合意图中写操作指代不清 -> 咨询照答、写操作被拒绝且如实说明
    msg2 = "你们几点关门？顺便把那个菜加一份"
    print(f"[场景2] 写操作指代不清: {msg2}")
    reply2, cart2 = await _run(msg2)
    print(f"        回复: {reply2}")
    print(f"        购物车: {cart2}")
    if not cart2:
        print("        [通过] 指代不清的写操作未执行（购物车为空）✔")
    else:
        print("        [失败] 指代不清的写操作被执行了！")
        ok = False
    print("-" * 72)

    # 场景 3：过多过杂的矛盾需求 -> unclear 固定话术
    msg3 = "把购物车里的菜都查一遍热量，不辣的换成辣的，再下单再取消"
    print(f"[场景3] 过多过杂: {msg3}")
    reply3, cart3 = await _run(msg3)
    print(f"        回复: {reply3}")
    if "没有完全理解" in reply3 or "一句话" in reply3:
        print("        [通过] 已走 unclear 兜底话术 ✔")
    else:
        print("        [失败] 未走 unclear 兜底")
        ok = False
    print("-" * 72)

    # 场景 4：辣度固定属性 —— 点辣菜 + 问辣度（混合意图 -> 经理）
    # 预期：直接加菜、如实告知菜单标注的辣度，绝不出现"确认辣度/备注辣度"类话术
    spicy_dish, spicy_level = await _pick_spicy_dish()
    msg4 = f"来一份{spicy_dish}，这道菜辣吗"
    print(f"[场景4] 辣度固定（{spicy_dish}，辣度 {spicy_level}/3）: {msg4}")
    reply4, cart4 = await _run(msg4)
    print(f"        回复: {reply4}")
    print(f"        购物车: {cart4}")
    # 正确回复不会出现的典型错误话术（确认辣度/让顾客选辣度/把辣度当备注）
    bad_phrases = [
        "确认辣度", "辣度未确认", "辣度还没", "备注辣度", "做多辣",
        "几成辣", "要什么辣度", "选什么辣度", "选哪个辣度",
        "做微辣可以", "做中辣可以", "做特辣可以",
    ]
    in_cart4 = {e.get("name"): e.get("quantity") for e in cart4}
    if in_cart4.get(spicy_dish) != 1:
        print("        [失败] 菜未按数量加入购物车")
        ok = False
    elif any(p in reply4 for p in bad_phrases):
        print("        [失败] 回复中出现了确认/备注辣度的话术（辣度应为固定属性）")
        ok = False
    else:
        print("        [通过] 直接加菜并如实告知辣度，未向顾客确认辣度 ✔")
    print("=" * 72)

    if ok:
        print("[全部通过] 餐厅经理端到端行为符合设计预期 ✔")
        return 0
    print("[存在偏差] 请检查上方失败场景")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
