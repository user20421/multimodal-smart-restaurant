"""
L1 正则快速路：用确定性规则处理高频简单意图，~0ms、不调 LLM。

原则：任何不确定（菜名零命中/多候选歧义/槽位缺失）都返回 None 让位给
L2 LLM Agent —— 宁可不办，不可错办。
"""
import re
from typing import Optional

from app.ai.agent.context import AgentContext
from app.ai.agent.tools import cart_tools as ct
from app.ai.agent.tools.menu_tools import resolve_dish
from app.ai.agent.tools.order_tools import (
    place_order_from_cart,
    query_orders_last_days,
    query_orders_on_date,
    query_recent_orders,
    query_today_orders,
)

# ============================================================
# 数量解析
# ============================================================

_CN_DIGIT = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}

_QTY_RE = r"(\d+|[零一二两三四五六七八九十]{1,3})"
# 非捕获版本：用于需要独立捕获数量与菜名的新模式（避免 _QTY_RE 内层括号错位）
_QTY_NC = r"(?:\d+|[零一二两三四五六七八九十]{1,3})"
_UNIT = r"(?:份|个|碗|盘|杯|串|例|斤|条|瓶|罐|盒)"
# 尾部语气/标点剥除：词组与单字混合，循环剥到干净为止
# （"来一份宫保鸡丁，谢谢" -> "来一份宫保鸡丁"；"不要宫保鸡丁了" -> "不要宫保鸡丁"）
_TAIL = r"(?:[。！!？?~，,]|啊|呀|呢|吧|了|哦|呗|哈|谢谢|谢了)+$"


def parse_quantity(text: str) -> Optional[int]:
    """解析数量（阿拉伯数字或 99 以内的中文数字）。解析失败返回 None。"""
    text = text.strip()
    if text.isdigit():
        n = int(text)
        return n if n > 0 else None
    if not text:
        return None
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_DIGIT.get(left, 1) if left else 1
        ones = _CN_DIGIT.get(right) if right else 0
        if (left and left not in _CN_DIGIT) or (right and right not in _CN_DIGIT):
            return None
        return tens * 10 + ones
    if text in _CN_DIGIT:
        n = _CN_DIGIT[text]
        return n if n > 0 else None
    return None


def _strip_tail(text: str) -> str:
    return re.sub(_TAIL, "", text.strip())


# ============================================================
# 意图模式
# ============================================================

# 清空购物车
_CLEAR_PATTERNS = [
    re.compile(r"^(?:请|麻烦)?(?:帮我|给我)?(?:清空|清除|清掉)(?:一下)?(?:我的)?购物车$"),
    re.compile(r"^(?:把)?(?:我的)?购物车(?:给)?(?:清空|清除|清空一下|清除一下|清掉)$"),
    # 口语："购物车不要了""把购物车里的菜都删了"
    # （尾部"了"会被 _strip_tail 先剥掉，故词表含裸"删/清"）
    re.compile(
        r"^(?:请|麻烦)?(?:帮我|给我)?(?:把|将)?(?:我的|我)?购物车(?:里(?:的)?菜)?"
        r"(?:都|全)?(?:删掉|删了|删|清了|清掉|清|不要了|不要)$"
    ),
    # 口语："重新点"（清空重来）
    re.compile(r"^(?:重新|重新来|重头来)(?:点|点餐|点菜)$"),
]

# 查看购物车
_VIEW_CART_PATTERNS = [
    re.compile(
        r"^(?:查看|看看|看下|看一下|打开)?(?:现在|目前)?(?:我的|我)?购物车(?:里)?"
        r"(?:有什么|有啥|有什么菜|有啥菜|里有什么|里有什么菜)?$"
    ),
    # 口语："我购物车呢"（尾部"呢"可能已被 _strip_tail 剥除）
    re.compile(r"^(?:我的|我)?购物车呢?$"),
    # 口语："我点了什么/我点了啥菜"
    re.compile(r"^(?:我|我们)(?:都)?点了(?:些)?(?:什么|啥)(?:菜)?$"),
]

# 下单 / 结算（词表与 order_tools._ORDER_WORDS 保持一致）
_PLACE_ORDER_PATTERN = re.compile(
    r"^(?:就这些|就这样|好了|行了|可以了)?(?:吧)?[,，]?(?:请|麻烦)?(?:我|我们)?"
    r"(?:要|想|想要)?(?:帮我|给我|帮忙)?(?:可以|能)?"
    r"(?:确认下单|提交订单|结算|买单|结账|下单|付款|付钱|交钱)$"
)

# 订单查询：最近 N 条 / 最近 N 天 / 今天 / 昨天·前天（具体某一天）
# 所有模式均为完全匹配（^...$ + match），只有整句就是一个明确的查询意图才执行，
# 避免“我昨天的订单能退款吗”这类句子被部分匹配误伤
_RECENT_ORDERS_PATTERN = re.compile(
    rf"^(?:查看|看看|看下|看一下|查一下|查询|帮我查查?|请问)?"
    rf"(?:我|我的)?最近(?:的)?{_QTY_RE}(?:条|笔|个)订单"
    rf"(?:有哪些|有什么|是什么|情况)?$"
)
_LAST_DAYS_ORDERS_PATTERN = re.compile(
    rf"^(?:查看|看看|看下|看一下|查一下|查询|帮我查查?|请问)?"
    rf"(?:我|我的)?最近{_QTY_RE}天(?:内|里)?(?:的)?订单"
    rf"(?:有哪些|有什么|是什么|情况)?$"
)
_TODAY_ORDERS_PATTERN = re.compile(r"^(?:查看|看看|看下|看一下)?(?:今天|今日)(?:的)?订单$")
# 具体某一天：“昨天的订单”“昨天有订单吗”“前天订单有哪些”等
_ON_DATE_ORDERS_PATTERNS = [
    re.compile(
        r"^(?:查看|看看|看下|看一下|查一下|查询|帮我查一下|请问)?"
        r"(?:我|我的)?(昨天|昨日|前天)(?:的)?订单"
        r"(?:有哪些|有什么|是什么|情况)?(?:吗|么|没|没有|呢)?$"
    ),
    re.compile(
        r"^(?:请问|请问一下)?(?:我|我的)?(昨天|昨日|前天)"
        r"(?:有没有|是否有|有|有没)(?:的)?订单(?:吗|么|呢)?$"
    ),
]
# “我的订单”入口（含快捷按钮的“查询我的订单/查询订单”）
_MY_ORDERS_PATTERN = re.compile(
    r"^(?:查看|看看|看下|看一下|查询|查一下|查下|查查|查|帮我查查?|请问)?(?:我的)?订单$"
)

# 换菜：把X换成Y / 把两份X换成一份Y / 把其中两份X换成一份Y（部分换）
_SWAP_PATTERN = re.compile(
    r"^(?:请|麻烦)?(?:帮我|给我)?(?:把|将)?(.+?)(?:换成|换为)(.+?)$"
)
# 改数量：X改成2份 / X调整为3份
_SET_TO_PATTERN = re.compile(
    rf"^(?:请|麻烦)?(?:帮我|给我)?(?:把|将)?(.+?)(?:改成|调整为){_QTY_RE}{_UNIT}?$"
)
# 只要 N 份：宫保鸡丁只要一份
_SET_QTY_PATTERN = re.compile(
    rf"^(?:请|麻烦)?(?:帮我|给我)?(?:把|将)?(.+?)(?:只要|只需要|就留|留){_QTY_RE}{_UNIT}?$"
)

# 减/删菜
_REMOVE_PATTERNS = [
    re.compile(
        r"^(?:请|麻烦)?(?:帮我|给我)?(?:把|将)?(.+?)(?:给我)?"
        r"(?:去掉|删掉|删除|拿掉|移除|不要了|不要)$"
    ),
    re.compile(r"^(?:请|麻烦)?(?:帮我|给我)?(?:去掉|删掉|删除|拿掉|移除|不要)(.+?)$"),
]

# 加菜：来三份宫保鸡丁 / 我要一份米饭 / 再加两个烤串 / 点一份汤 / 再来一份毛血旺
# 注意动词组长词必须前置（alternation 从左到右，"再加"会抢在"再加点"前匹配）
_ADD_PATTERN = re.compile(
    rf"^(?:请|麻烦)?(?:先|那就|那么|然后)?(?:我|我们)?(?:想|想要)?"
    rf"(?:帮我|给我|给我们|帮|给)?"
    rf"(?:再加点|再加|再来|再要|还要|多点|上一份|来|要|加|点|上|整|搞)"
    rf"{_QTY_RE}?{_UNIT}?(.+?)$"
)
# 裸数量加菜：一份宫保鸡丁 / 两碗米饭（整句就是"数量+菜名"）
_ADD_BARE_PATTERN = re.compile(rf"^({_QTY_NC}){_UNIT}(.+?)$")
# 倒装加菜：白米饭两份 / 宫保鸡丁来两份 / 酸菜鱼来一条
_ADD_INVERTED_PATTERN = re.compile(rf"^(.+?)(?:来)?({_QTY_NC}){_UNIT}$")


# ============================================================
# 主入口
# ============================================================


async def try_handle(ctx: AgentContext, message: str) -> Optional[str]:
    """尝试用快速路处理消息。返回回复文本；无法确定时返回 None（让位给 LLM Agent）。"""
    text = _strip_tail(message)
    if not text:
        return None

    # 1. 清空购物车：高危操作，口令必须逐字精确（整句就是"清空购物车"五个字才执行）；
    #    其他清空意图的变体表述一律不执行，统一引导用户说出准确口令
    if ct.is_clear_command(text):
        if not ctx.cart:
            return "购物车本来就是空的，去看看有什么想吃的吧。"
        ct.cart_clear(ctx)
        return "好的，购物车已清空。"
    if any(p.match(text) for p in _CLEAR_PATTERNS):
        return ct.CLEAR_ASK_TEXT

    # 2. 查看购物车
    if any(p.match(text) for p in _VIEW_CART_PATTERNS):
        return ct.cart_summary_text(ctx.cart)

    # 3. 下单 / 结算（fastpath 为顺序执行，复用请求会话即可）
    if _PLACE_ORDER_PATTERN.match(text):
        return await place_order_from_cart(ctx, db=ctx.db)

    # 4. 订单查询
    for p in _ON_DATE_ORDERS_PATTERNS:
        m = p.match(text)
        if m:
            # 具体某一天：严格限定当日，不带出其他天的订单
            days_ago = 2 if m.group(1) == "前天" else 1
            return await query_orders_on_date(ctx.db, ctx.user_id, days_ago)
    m = _LAST_DAYS_ORDERS_PATTERN.match(text)
    if m:
        days = parse_quantity(m.group(1))
        if days is None:
            return None
        return await query_orders_last_days(ctx.db, ctx.user_id, days)
    m = _RECENT_ORDERS_PATTERN.match(text)
    if m:
        n = parse_quantity(m.group(1))
        if n is None:
            return None
        return await query_recent_orders(ctx.db, ctx.user_id, n)
    if _TODAY_ORDERS_PATTERN.match(text):
        return await query_today_orders(ctx.db, ctx.user_id)
    if _MY_ORDERS_PATTERN.match(text):
        return await query_recent_orders(ctx.db, ctx.user_id, 5)

    # 5. 改数量（X改成N份 / X只要N份）
    m = _SET_TO_PATTERN.match(text)
    if m:
        qty = parse_quantity(m.group(2))
        if qty is None:
            return None
        return await _handle_set_quantity(ctx, m.group(1), qty)

    # 6. 换菜（把X换成Y / 把N份X换成M份Y，支持部分换）
    m = _SWAP_PATTERN.match(text)
    if m:
        return await _handle_swap(ctx, m.group(1), m.group(2))

    # 7. 只要 N 份
    m = _SET_QTY_PATTERN.match(text)
    if m:
        qty = parse_quantity(m.group(2))
        if qty is None:
            return None
        return await _handle_set_quantity(ctx, m.group(1), qty)

    # 8. 减/删菜
    for p in _REMOVE_PATTERNS:
        m = p.match(text)
        if m:
            return await _handle_remove(ctx, m.group(1))

    # 9. 加菜
    m = _ADD_PATTERN.match(text)
    if m:
        qty = parse_quantity(m.group(1)) if m.group(1) else 1
        if m.group(1) and qty is None:
            return None
        return await _handle_add(ctx, m.group(2), qty or 1)

    # 10. 裸数量加菜（一份宫保鸡丁）：菜名必须经 resolve_dish 唯一命中，
    #     咨询类句子（"一份够几个人吃"）会因零命中自然让位给 L2
    m = _ADD_BARE_PATTERN.match(text)
    if m:
        qty = parse_quantity(m.group(1))
        if qty is None:
            return None
        return await _handle_add(ctx, m.group(2), qty)

    # 11. 倒装加菜（白米饭两份 / 宫保鸡丁来两份）
    m = _ADD_INVERTED_PATTERN.match(text)
    if m:
        qty = parse_quantity(m.group(2))
        if qty is None:
            return None
        return await _handle_add(ctx, m.group(1), qty)

    return None


# ============================================================
# 各意图处理器
# ============================================================


async def _handle_add(ctx: AgentContext, dish_keyword: str, qty: int) -> Optional[str]:
    item, candidates = await resolve_dish(ctx.db, dish_keyword)
    if item is None:
        # 零命中或多候选歧义 -> 让位给 LLM 消歧
        return None
    ct.cart_add(ctx, item, qty)
    return f"好的，已为您加入 {qty} 份{item.name}（¥{item.price}/份）。"


async def _handle_remove(ctx: AgentContext, dish_keyword: str) -> Optional[str]:
    item, candidates = await resolve_dish(ctx.db, dish_keyword)
    if item is None:
        entry = ct.cart_find_by_name(ctx, dish_keyword.strip())
        if entry:
            ct.cart_remove(ctx, entry["menu_item_id"])
            return f"好的，已将{entry['name']}从购物车移除。"
        return None  # 歧义/零命中 -> 让位
    if ct.cart_remove(ctx, item.id):
        return f"好的，已将{item.name}从购物车移除。"
    return f"您的购物车里没有{item.name}，需要我帮您加一份吗？"


async def _handle_set_quantity(
    ctx: AgentContext, dish_keyword: str, qty: int
) -> Optional[str]:
    item, _ = await resolve_dish(ctx.db, dish_keyword)
    if item is None:
        return None
    if not ct.cart_find(ctx, item.id):
        return f"您的购物车里没有{item.name}，需要我帮您加上吗？"
    ct.cart_set_quantity(ctx, item.id, qty)
    return f"好的，{item.name}的数量已调整为 {qty} 份。"


async def _handle_swap(ctx: AgentContext, from_part: str, right: str) -> Optional[str]:
    """换菜：整项换（把X换成Y）或部分换（把[其中]N份X换成M份Y）。

    语义约定：
    - 左侧带数量 -> 部分换：X 减少 N 份，Y 增加 M 份（M 缺省 = N）
    - 左侧不带数量 -> 整项换：X 全部移除，Y 增加 M 份（M 缺省 = X 原有数量）
    - 右侧是纯数量（把X换成2份）-> 视为改数量
    任何一步不确定（菜名零命中/歧义、数量解析失败、购物车数量不够且表达矛盾）
    都返回 None 让位给 L2，绝不换错。
    """
    from_part = from_part.strip()
    right = right.strip()

    # 左侧数量前缀：[其中]N份X
    from_qty: Optional[int] = None
    from_kw = from_part
    m = re.match(rf"^(?:其中)?{_QTY_RE}{_UNIT}(.+)$", from_part)
    if m:
        from_qty = parse_quantity(m.group(1))
        if from_qty is None:
            return None
        from_kw = m.group(2).strip()

    # 右侧是纯数量 -> 改数量（“把X换成2份”）；左侧也带数量则表达矛盾 -> 让位
    m = re.match(rf"^{_QTY_RE}{_UNIT}?$", right)
    if m:
        if from_qty is not None:
            return None
        qty = parse_quantity(m.group(1))
        if qty is None:
            return None
        return await _handle_set_quantity(ctx, from_kw, qty)

    # 右侧数量前缀：[来|要]M份Y
    to_qty: Optional[int] = None
    to_kw = right
    m = re.match(rf"^(?:来|要)?{_QTY_RE}{_UNIT}(.+)$", right)
    if m:
        to_qty = parse_quantity(m.group(1))
        if to_qty is None:
            return None
        to_kw = m.group(2).strip()

    from_item, _ = await resolve_dish(ctx.db, from_kw)
    if from_item is None:
        return None
    to_item, _ = await resolve_dish(ctx.db, to_kw)
    if to_item is None:
        return None  # 目标菜歧义/不存在 -> 让位，避免换错
    if from_item.id == to_item.id:
        return f"{from_item.name}和要换的是同一道菜，无需更换。"

    existing = ct.cart_find(ctx, from_item.id)
    if not existing:
        return f"您的购物车里没有{from_item.name}，无从替换。需要直接帮您加点别的吗？"
    existing_qty = int(existing.get("quantity", 0))

    if from_qty is None:
        # 整项换：移除全部 X，Y 数量为右侧指定值或 X 原有数量
        final_qty = to_qty or existing_qty
        ct.cart_remove(ctx, from_item.id)
        ct.cart_add(ctx, to_item, final_qty)
        return f"好的，已把{from_item.name}换成 {final_qty} 份{to_item.name}。"

    # 部分换：购物车数量必须足够
    if existing_qty < from_qty:
        return (
            f"您的购物车里只有 {existing_qty} 份{from_item.name}，"
            f"不够换出 {from_qty} 份。需要我按实际数量来调整吗？"
        )
    final_to_qty = to_qty or from_qty
    remaining = existing_qty - from_qty
    if remaining > 0:
        ct.cart_set_quantity(ctx, from_item.id, remaining)
    else:
        ct.cart_remove(ctx, from_item.id)
    ct.cart_add(ctx, to_item, final_to_qty)
    remain_text = f"（{from_item.name}还剩 {remaining} 份）" if remaining > 0 else ""
    return (
        f"好的，已把其中 {from_qty} 份{from_item.name}换成 {final_to_qty} 份{to_item.name}"
        f"{remain_text}。"
    )
