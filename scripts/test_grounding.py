# -*- coding: utf-8 -*-
"""
"简短确认被幻觉接单"问题的实机回归检查（联网调用百炼，只读、不落库）：

还原翻车现场——上一轮助手问了是非确认（"请问您是要把2份白米饭和1份肺片
加入购物车吗？"），用户只回"是的"。期望：路由到 chitchat/unclear，回复
如实说明尚未执行任何操作并引导用户用完整的一句话说出需求；
绝不出现"已为您记录"类未接地声称。

直接运行: python scripts/test_grounding.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.ai.agent.context import AgentContext
from app.ai.agent.graph import run_graph

HISTORY = [
    {"role": "user", "content": "2份白米饭和1份肺片"},
    {"role": "assistant", "content": "请问您是要把2份白米饭和1份肺片加入购物车吗？"},
]

BANNED = ["已为您记录", "已经记录", "已记下", "已加", "已下单", "已移除", "帮您记着", "已确认", "已加入"]


async def main() -> int:
    # db=None：chitchat/unclear 路由不触发任何工具；即使误路由，工具层 guard 也会拦截写操作
    ctx = AgentContext(db=None, user_id=0, message="是的", cart=[])
    reply = await run_graph(ctx, "是的", HISTORY)
    print("用户: 是的")
    print(f"小餐: {reply}")
    hits = [w for w in BANNED if w in reply]
    if hits:
        print(f"[FAIL] 出现未接地声称: {hits}")
        return 1
    print("[PASS] 未声称已执行任何操作 ✔")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
