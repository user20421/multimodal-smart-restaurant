# -*- coding: utf-8 -*-
"""
路由分类器（模型 A + router.md 提示词）边界实测校准脚本

用一组带期望标签的句子真实调用分类模型，验证六类路由（含"餐厅经理" manager）
的划分是否符合设计阈值：
- 同类多操作不超过专员上限（cart ≤2 件，其余 ≤3 件）且简单 -> 留在专员；超上限 -> manager
- 单件复杂操作能理解 -> 专员；理解不了 -> manager
- 跨类别混合、每件事都明确、总事项 ≤3 件 -> manager；总事项 ≥4 件 -> unclear
- 疑问/反问/质疑句式里出现的菜品和数量不是写操作指令 -> 按实际语气分类，拿不准 -> unclear
- 过多过杂 / 矛盾 / 指代不清 -> unclear（宁愿不做，不可做错）

配置与提示词均复用 backend 真实代码（app.ai.config / prompts/router.md /
graph._parse_route），模型 A 名称读 backend/.env 的 BAILIAN_LLM_MODEL。

用法:
    python scripts/test_router.py
"""
import sys
import time
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ai import config  # noqa: E402
from app.ai.agent.graph import _parse_route  # noqa: E402
from app.ai.agent.prompts import ROUTER_PROMPT  # noqa: E402

# (测试句子, 可接受的标签集合, 说明)
CASES = [
    # ---- 简单单意图 -> 专员（线上多被 L1 快速路拦截，router 也应分对）----
    ("来三份宫保鸡丁", {"cart"}, "单意图加菜"),
    ("清空购物车", {"cart"}, "单意图清空"),
    ("确认下单", {"cart"}, "单意图下单"),
    ("最近五天的订单", {"order"}, "单意图查单"),
    ("你们几点关门", {"knowledge"}, "单意图咨询"),
    ("你好", {"chitchat"}, "闲聊"),
    # ---- 同类多操作（cart ≤2 件、每件明确）-> 仍归专员 ----
    ("来一份麻婆豆腐和两份宫保鸡丁", {"cart"}, "同类2件加菜"),
    ("来一份西瓜汁和4份白米饭", {"cart"}, "同类2件加菜（西瓜汁+米饭）"),
    ("把宫保鸡丁改成三份，再把麻婆豆腐移除", {"cart"}, "同类2件改+删"),
    # ---- 单件复杂但能理解 -> 专员 ----
    ("把其中两份宫保鸡丁换成一份麻婆豆腐", {"cart"}, "部分换菜"),
    # ---- 同类操作超 cart 上限（≥3 件）-> 经理 ----
    ("来一份麻婆豆腐、两份宫保鸡丁，再加一碗米饭", {"manager"}, "同类3件加菜超上限"),
    ("麻婆豆腐、宫保鸡丁、鱼香肉丝、水煮鱼各来一份", {"manager"}, "同类4件加菜"),
    # ---- 跨类别混合（总事项 ≤3 件）-> 经理 ----
    ("看看我昨天的订单，顺便再来一杯酸梅汤", {"manager"}, "查单+加菜"),
    ("宫保鸡丁辣不辣？不辣的话给我来两份", {"manager"}, "条件咨询+加菜"),
    ("我最近的订单送到了吗？另外帮我把购物车清空", {"manager"}, "查单+清空"),
    # ---- 跨类别混合但总事项 ≥4 件 -> unclear ----
    ("你们今天的营业时间是什么，帮我来一份麻婆豆腐和2份宫保鸡丁，再来一份白米饭",
     {"unclear"}, "咨询+加3样共4件"),
    ("你们几点关门，来一份宫保鸡丁和一份夫妻肺片，再看下我的订单",
     {"unclear"}, "混合4件超上限"),
    # ---- 疑问/质疑句式不是写操作指令 ----
    # 疑问/质疑句：unclear 或 chitchat 均可（两者都不会执行写操作），绝不许 cart
    ("我怎么是来一份宫保鸡丁和一份夫妻肺片", {"unclear", "chitchat"}, "疑问句非指令"),
    ("为什么我的订单里有两份宫保鸡丁", {"order"}, "疑问句查订单"),
    # ---- 指代不清 / 无法执行 -> unclear ----
    ("帮我把那个菜再加一份", {"unclear"}, "指代不清"),
    ("随便来点吃的", {"unclear"}, "意图不明"),
    # ---- 过多过杂 / 矛盾 -> unclear ----
    ("把购物车里的菜都查一遍热量，不辣的换成辣的，再下单再取消", {"unclear"}, "过多过杂+矛盾"),
]

# 边界与混合类句子重复次数（检验模型 A 分类稳定性）；简单句只跑 1 次
REPEAT_FOR = {"同类2件加菜", "同类3件加菜超上限", "同类4件加菜", "咨询+加3样共4件", "混合4件超上限",
              "疑问句非指令", "疑问句查订单", "查单+加菜", "条件咨询+加菜",
              "查单+清空", "过多过杂+矛盾"}
REPEAT_TIMES = 2


def classify(message: str) -> tuple[str, str]:
    """调用分类模型，返回 (解析后的标签, 模型原始输出)。"""
    resp = requests.post(
        f"{config.BAILIAN_BASE_URL}/chat/completions",
        json={
            "model": config.BAILIAN_LLM_MODEL,
            "messages": [
                {"role": "system", "content": ROUTER_PROMPT},
                {"role": "user", "content": message},
            ],
            "enable_thinking": False,
            "temperature": 0.0,
        },
        headers={
            "Authorization": f"Bearer {config.BAILIAN_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    resp.raise_for_status()
    raw = (resp.json()["choices"][0]["message"].get("content") or "").strip()
    return _parse_route(raw), raw


def main() -> int:
    if not config.BAILIAN_API_KEY or not config.BAILIAN_LLM_MODEL:
        print("[失败] 未配置 DASHSCOPE_API_KEY 或 BAILIAN_LLM_MODEL")
        return 1

    print(f"分类模型(A): {config.BAILIAN_LLM_MODEL}")
    print(f"测试用例: {len(CASES)} 句（边界/混合类重复 {REPEAT_TIMES} 次检验稳定性）")
    print("=" * 78)

    total, passed = 0, 0
    for sentence, expected, note in CASES:
        times = REPEAT_TIMES if note in REPEAT_FOR else 1
        results = []
        for _ in range(times):
            try:
                route, raw = classify(sentence)
            except Exception as e:
                route, raw = f"<error:{type(e).__name__}>", ""
            results.append((route, raw))
            time.sleep(0.3)  # 轻微限速，避免触发限流
        for route, raw in results:
            total += 1
            ok = route in expected
            passed += ok
            mark = "PASS" if ok else "FAIL"
            short = sentence if len(sentence) <= 30 else sentence[:30] + "…"
            expect_text = "/".join(sorted(expected))
            print(f"[{mark}] {note:<14} | 期望 {expect_text:<13} | 实际 {route:<9} | {short}")
            if not ok and raw and raw != route:
                print(f"       模型原始输出: {raw[:60]!r}")

    print("=" * 78)
    print(f"结果: {passed}/{total} 通过")
    if passed == total:
        print("[通过] 路由阈值符合设计预期 ✔")
        return 0
    print("[存在偏差] 请根据上方 FAIL 项调整 router.md 的阈值表述或示例")
    return 1


if __name__ == "__main__":
    sys.exit(main())
