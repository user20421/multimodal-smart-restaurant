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
        ("unclear", "unclear"),
        ("cart。", "cart"),
        (" order ", "order"),
        ("CART", "cart"),
        ('"knowledge"', "knowledge"),
        # 无法识别 -> 降级 unclear（拿不准就不办）
        ("随便", "unclear"),
        ("", "unclear"),
        ("我认为是cart", "cart"),  # 包含匹配兜底
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
