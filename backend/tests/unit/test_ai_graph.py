"""
多智能体图：路由标签解析单元测试（纯函数，无需 LLM/DB）
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from app.ai.agent.graph import _parse_route
from app.ai.sanitize import sanitize_reply, strip_emoji


@pytest.mark.parametrize(
    "text,expected",
    [
        ("cart", "cart"),
        ("order", "order"),
        ("knowledge", "knowledge"),
        ("chitchat", "chitchat"),
        ("manager", "manager"),
        ("unclear", "unclear"),
        ("cart。", "cart"),
        (" order ", "order"),
        ("CART", "cart"),
        ("MANAGER", "manager"),
        ('"knowledge"', "knowledge"),
        (" manager ", "manager"),
        # 无法识别 -> 降级 unclear（拿不准就不办）
        ("随便", "unclear"),
        ("", "unclear"),
        ("我认为是cart", "cart"),  # 包含匹配兜底
        ("我认为是manager", "manager"),  # 包含匹配兜底
    ],
)
def test_parse_route(text, expected):
    assert _parse_route(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("辣度 3/3，特辣🌶️", "辣度 3/3，特辣"),
        ("你好😄，想吃什么？", "你好，想吃什么？"),
        ("宫保鸡丁x2，合计 ¥76", "宫保鸡丁x2，合计 ¥76"),  # 中文与常规符号不受影响
        ("纯文本无表情", "纯文本无表情"),
        ("", ""),
    ],
)
def test_strip_emoji(text, expected):
    assert strip_emoji(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("（微笑）您问的是昨天的订单。", "您问的是昨天的订单。"),
        ("好的(点头)，马上为您查询。", "好的，马上为您查询。"),
        ("（微笑，语气轻快）欢迎光临！", "欢迎光临！"),
        ("订单（已确认）共 ¥186", "订单（已确认）共 ¥186"),  # 正常括号不受影响
        ("这道菜（微辣）很下饭", "这道菜（微辣）很下饭"),      # 微辣 ≠ 微笑
        ("（微笑）😄你好", "你好"),                            # 舞台指示 + emoji 一起清
    ],
)
def test_sanitize_reply_stage_directions(text, expected):
    assert sanitize_reply(text) == expected


# ---------------------------------------------------------------------------
# 节点消息构造：确定性提示注入（防"悬空确认"与"未执行却声称完成"两类问题）
# ---------------------------------------------------------------------------
from app.ai.agent.context import AgentContext
from app.ai.agent.graph import (
    _NO_WRITE_GROUNDING_NOTE,
    _WRITE_NODE_NOTE,
    _cart_context_message,
    _no_write_context_message,
    _readonly_context_message,
)


def _ctx() -> AgentContext:
    return AgentContext(db=None, user_id=1, message="", cart=[])


def test_cart_context_message_injects_write_note_and_snapshot():
    ctx = _ctx()
    ctx.cart = [{"menu_item_id": 1, "name": "宫保鸡丁", "quantity": 2, "unit_price": 38.0}]
    msg = _cart_context_message(ctx, "来两份宫保鸡丁")
    assert msg.content.startswith(_WRITE_NODE_NOTE)
    assert "[上下文]" in msg.content and "宫保鸡丁" in msg.content  # 购物车快照保留
    assert msg.content.endswith("来两份宫保鸡丁")  # 用户原句完整保留在最后
    assert _NO_WRITE_GROUNDING_NOTE not in msg.content  # 写节点不注入无写提示


def test_write_note_covers_two_class_rules():
    assert "是非确认" in _WRITE_NODE_NOTE        # 禁止悬空确认类
    assert "不得声称已完成" in _WRITE_NODE_NOTE  # 未接地不声称类


def test_no_write_context_message_wraps_user_sentence():
    msg = _no_write_context_message("是的")
    assert msg.content == f"{_NO_WRITE_GROUNDING_NOTE}\n\n是的"
    assert msg.content.startswith("[系统提示")


def test_no_write_note_requires_honesty_and_full_sentence_guidance():
    assert "尚未" in _NO_WRITE_GROUNDING_NOTE          # 如实说明未执行
    assert "一句完整的话" in _NO_WRITE_GROUNDING_NOTE  # 引导完整句
    assert "写操作" in _NO_WRITE_GROUNDING_NOTE


def test_readonly_context_message_combines_note_and_snapshot():
    ctx = _ctx()
    ctx.cart = [{"menu_item_id": 2, "name": "米饭", "quantity": 1, "unit_price": 2.0}]
    msg = _readonly_context_message(ctx, "那笔订单呢")
    assert msg.content.startswith(_NO_WRITE_GROUNDING_NOTE)
    assert "米饭" in msg.content
    assert msg.content.endswith("那笔订单呢")


def test_readonly_message_empty_cart_snapshot():
    msg = _readonly_context_message(_ctx(), "随便看看")
    assert "购物车是空的" in msg.content

