"""
购物车工具

cart_* 开头的为纯函数（直接操作 ctx.cart 快照），供 fastpath 与工具层共用；
build_cart_tools 生成 LLM 可调用的 LangChain 工具（闭包持有 ctx）。

注意：购物车单一事实源是前端 Pinia，这里只在请求快照副本上修改，
最终结果由路由层通过响应（done.cart）回传给前端落地。
"""
from typing import Optional

from langchain_core.tools import tool

from app.ai.agent.context import AgentContext
from app.ai.agent.tools.menu_tools import resolve_dish
from app.core.database import AsyncSessionLocal
from app.models.menu import MenuItem
from app.utils.formatters import fmt_price

# ============================================================
# 写操作"本句表达"守卫（确定性硬约束，不依赖 LLM 自觉遵守提示词）
# ============================================================

# 清空/删除类动作词
_CLEAR_WORDS = ("清空", "清除", "删除", "删掉", "去掉", "拿掉", "移除", "不要")


def write_refusal_text(example: str) -> str:
    """写操作被拒绝时的引导话术（让 LLM 结合上下文追问用户）。"""
    return (
        "未执行任何操作。规则：增删改/下单等写操作只能依据用户当前这一句话执行，"
        "句中必须明确写出操作对象（如菜品名称）和动作；指代历史内容或简短确认"
        "（如“移除”“好的”“是的”）一律不得执行。"
        f"请结合对话上下文向用户确认他的意图，并请他用一句话说清楚，例如：“{example}”。"
        "特别注意：你的回复必须如实告知用户“还没有执行”，"
        "严禁出现“已为您下单”“我这就为您下单”“已移除”“已加菜”等声称已完成的表述。"
    )


def guard_write_op(ctx: AgentContext, *must_hit: str, example: str) -> Optional[str]:
    """增删改/下单等写操作的前置校验：操作对象与动作必须由用户当前这句话明确表达。

    每个参数为必须出现的关键词；全部命中才返回 None 放行，否则返回引导话术（不执行）。
    即使上一轮是助手主动给出的选项，用户只回复“移除”“好的”这类简短确认也不算数。
    """
    msg = ctx.message or ""
    if all(kw in msg for kw in must_hit):
        return None
    return write_refusal_text(example)


# ============================================================
# 纯函数：购物车快照操作（fastpath 与工具共用）
# ============================================================


def cart_find(ctx: AgentContext, menu_item_id: int) -> Optional[dict]:
    for entry in ctx.cart:
        if entry.get("menu_item_id") == menu_item_id:
            return entry
    return None


def cart_find_by_name(ctx: AgentContext, name: str) -> Optional[dict]:
    for entry in ctx.cart:
        if entry.get("name") == name:
            return entry
    return None


def cart_add(ctx: AgentContext, item: MenuItem, quantity: int) -> None:
    entry = cart_find(ctx, item.id)
    if entry:
        entry["quantity"] = int(entry.get("quantity", 0)) + quantity
    else:
        ctx.cart.append(
            {
                "menu_item_id": item.id,
                "name": item.name,
                "quantity": quantity,
                "unit_price": item.price,
            }
        )
    ctx.dirty = True


def cart_remove(ctx: AgentContext, menu_item_id: int) -> bool:
    before = len(ctx.cart)
    ctx.cart[:] = [e for e in ctx.cart if e.get("menu_item_id") != menu_item_id]
    if len(ctx.cart) < before:
        ctx.dirty = True
        return True
    return False


def cart_set_quantity(ctx: AgentContext, menu_item_id: int, quantity: int) -> bool:
    """设置数量；quantity <= 0 等价于移除。"""
    if quantity <= 0:
        return cart_remove(ctx, menu_item_id)
    entry = cart_find(ctx, menu_item_id)
    if not entry:
        return False
    entry["quantity"] = quantity
    ctx.dirty = True
    return True


def cart_clear(ctx: AgentContext) -> None:
    if ctx.cart:
        ctx.cart.clear()
        ctx.dirty = True


def cart_summary_text(cart: list) -> str:
    if not cart:
        return "购物车是空的。"
    lines = [f"- {e['name']} ×{e['quantity']}（¥{fmt_price(e['unit_price'])}/份）" for e in cart]
    total = sum(float(e["unit_price"]) * int(e["quantity"]) for e in cart)
    return "当前购物车：\n" + "\n".join(lines) + f"\n合计约 ¥{fmt_price(total)}"


# ============================================================
# LangChain 工具（LLM 调用）
# ============================================================


def build_cart_tools(ctx: AgentContext) -> list:
    @tool("add_to_cart")
    async def add_to_cart(dish_name: str, quantity: int = 1) -> str:
        """把菜品加入购物车（或在已有数量上累加）。
        dish_name 为菜品名称，quantity 为正整数份数。
        数量不明确时必须先向用户确认，不要自行猜测。
        注意：dish_name 必须出现在用户当前这句话里，否则工具会拒绝执行。
        """
        refusal = guard_write_op(ctx, dish_name, example=f"来两份{dish_name}")
        if refusal:
            return refusal
        if quantity <= 0:
            return "数量必须为正整数，未执行任何操作。"
        async with AsyncSessionLocal() as db:
            item, candidates = await resolve_dish(db, dish_name)
        if item is None:
            if candidates:
                names = "、".join(c.name for c in candidates[:5])
                return f"“{dish_name}”有歧义，候选：{names}。请向用户确认后再执行。"
            return f"菜单中没有“{dish_name}”，未执行任何操作。"
        cart_add(ctx, item, quantity)
        return f"已加入 {quantity} 份{item.name}（¥{fmt_price(item.price)}/份）。"

    @tool("remove_from_cart")
    async def remove_from_cart(dish_name: str) -> str:
        """把菜品从购物车中移除（整项删除）。
        注意：dish_name 必须出现在用户当前这句话里，否则工具会拒绝执行。
        """
        refusal = guard_write_op(ctx, dish_name, example=f"把{dish_name}移除")
        if refusal:
            return refusal
        async with AsyncSessionLocal() as db:
            item, candidates = await resolve_dish(db, dish_name)
        target = item
        if target is None:
            # 菜品可能已不在菜单但仍躺在购物车里，按购物车里的名字再试一次
            entry = cart_find_by_name(ctx, dish_name.strip())
            if entry:
                cart_remove(ctx, entry["menu_item_id"])
                return f"已将“{entry['name']}”从购物车移除。"
            if candidates:
                names = "、".join(c.name for c in candidates[:5])
                return f"“{dish_name}”有歧义，候选：{names}。请向用户确认后再执行。"
            return f"没有找到“{dish_name}”，未执行任何操作。"
        if cart_remove(ctx, target.id):
            return f"已将“{target.name}”从购物车移除。"
        return f"购物车中没有“{target.name}”，未执行任何操作。"

    @tool("set_dish_quantity")
    async def set_dish_quantity(dish_name: str, quantity: int) -> str:
        """把购物车中某菜品的数量设置为指定值；quantity 为 0 时等价于移除。
        仅当用户明确给出目标数量时使用。
        注意：dish_name 必须出现在用户当前这句话里，否则工具会拒绝执行。
        """
        refusal = guard_write_op(ctx, dish_name, example=f"把{dish_name}改成2份")
        if refusal:
            return refusal
        if quantity < 0:
            return "数量不能为负数，未执行任何操作。"
        async with AsyncSessionLocal() as db:
            item, candidates = await resolve_dish(db, dish_name)
        target = item
        if target is None:
            entry = cart_find_by_name(ctx, dish_name.strip())
            if entry:
                cart_set_quantity(ctx, entry["menu_item_id"], quantity)
                return f"已将“{entry['name']}”的数量设置为 {quantity}。"
            if candidates:
                names = "、".join(c.name for c in candidates[:5])
                return f"“{dish_name}”有歧义，候选：{names}。请向用户确认后再执行。"
            return f"没有找到“{dish_name}”，未执行任何操作。"
        if cart_set_quantity(ctx, target.id, quantity):
            action = "移除" if quantity == 0 else f"数量设置为 {quantity}"
            return f"已将“{target.name}”{action}。"
        return f"购物车中没有“{target.name}”，未执行任何操作。"

    @tool("clear_cart")
    async def clear_cart_tool() -> str:
        """清空购物车（仅当用户明确要求时）。
        注意：用户当前这句话必须同时包含"购物车"和清空类动作词，否则工具会拒绝执行。
        """
        msg = ctx.message or ""
        if "购物车" not in msg or not any(w in msg for w in _CLEAR_WORDS):
            return write_refusal_text("清空购物车")
        if not ctx.cart:
            return "购物车本来就是空的。"
        cart_clear(ctx)
        return "购物车已清空。"

    @tool("view_cart")
    async def view_cart() -> str:
        """查看当前购物车内容。"""
        return cart_summary_text(ctx.cart)

    return [add_to_cart, remove_from_cart, set_dish_quantity, clear_cart_tool, view_cart]
