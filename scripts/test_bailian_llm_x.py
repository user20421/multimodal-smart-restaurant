# -*- coding: utf-8 -*-
"""
百炼更强模型（BAILIAN_LLM_MODEL_X，"餐厅经理"混合意图专用）连通性与参数兼容性测试

验证三件事：
1. 基本调用（不带 enable_thinking）是否正常——get_chat_llm_x 的默认形态
2. 带 enable_thinking=false 的对照调用是否被接口拒绝——决定能否复用该参数
3. 流式调用是否正常——经理节点流式输出依赖此能力

配置读取复用 app.ai.config（.env 优先，环境变量兜底；双模型强绑定校验也会顺带验证）。

用法:
    python scripts/test_bailian_llm_x.py
"""
import sys
import time
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ai import config  # noqa: E402

PROMPT = "用一句话介绍川菜的特点。"
API_URL_SUFFIX = "/chat/completions"


def _post(payload: dict) -> requests.Response:
    return requests.post(
        f"{config.BAILIAN_BASE_URL}{API_URL_SUFFIX}",
        json=payload,
        headers={
            "Authorization": f"Bearer {config.BAILIAN_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=120,
    )


def _extract(resp: requests.Response) -> str:
    data = resp.json()
    return (data["choices"][0]["message"].get("content") or "").strip()


def main() -> int:
    if not config.BAILIAN_API_KEY:
        print("[失败] 未找到 DASHSCOPE_API_KEY（开发模式请设为系统环境变量）")
        return 1
    if not config.BAILIAN_LLM_MODEL_X:
        print("[失败] 未在 backend/.env 配置 BAILIAN_LLM_MODEL_X")
        return 1

    model = config.BAILIAN_LLM_MODEL_X
    print(f"测试模型(X): {model}")
    print(f"API Key: {config.BAILIAN_API_KEY[:8]}...{config.BAILIAN_API_KEY[-4:]}")
    print(f"统一提问: {PROMPT}")
    print("=" * 60)

    ok = True

    # 1. 基本调用（不带 enable_thinking）—— get_chat_llm_x 的实际形态
    print("[1/3] 基本调用（不带 enable_thinking）...")
    try:
        start = time.perf_counter()
        resp = _post({"model": model, "messages": [{"role": "user", "content": PROMPT}]})
        elapsed = time.perf_counter() - start
        if resp.status_code != 200:
            print(f"      [失败] HTTP {resp.status_code}: {resp.text[:300]}")
            ok = False
        else:
            answer = _extract(resp)
            print(f"      [成功] 耗时 {elapsed:.2f}s，回答: {answer[:80]}")
            if any(mark in answer for mark in ("思考", "（是的", "（输出")):
                print("      [提醒] 回答中疑似混入思考链痕迹，请关注该模型是否需要显式关闭思考")
    except requests.RequestException as e:
        print(f"      [失败] {type(e).__name__}: {e}")
        ok = False

    # 2. 对照：带 enable_thinking=false（确认该参数的行为差异）
    # 实测结论（2026-08-20 探针验证）：
    # - 不传参数：模型默认开启思考，思考链在独立 reasoning_content 字段（不混入 content），
    #   usage 中可见 reasoning_tokens 计费
    # - enable_thinking=false：reasoning_content 字段完全消失，token 大幅节省，但模型明显降智
    # get_chat_llm_x 维持不传（默认开思考），保住经理节点的编排质量
    print("[2/3] 对照调用（带 enable_thinking=false）...")
    try:
        resp = _post({
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            "enable_thinking": False,
        })
        if resp.status_code != 200:
            print(f"      [结论] 接口拒绝该参数（HTTP {resp.status_code}），get_chat_llm_x 保持不传是对的")
        else:
            msg = resp.json()["choices"][0]["message"]
            has_reasoning = "reasoning_content" in msg
            print(f"      [结论] 接口接受该参数；关闭思考后 reasoning_content 字段{'仍存在' if has_reasoning else '已消失'}")
    except requests.RequestException as e:
        print(f"      [结论] 调用异常（{type(e).__name__}: {e}），get_chat_llm_x 保持不传是对的")

    # 3. 流式调用
    print("[3/3] 流式调用（stream=true）...")
    try:
        start = time.perf_counter()
        resp = _post({
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            "stream": True,
        })
        elapsed = time.perf_counter() - start
        if resp.status_code != 200:
            print(f"      [失败] HTTP {resp.status_code}: {resp.text[:300]}")
            ok = False
        else:
            chunks = sum(1 for line in resp.text.splitlines() if line.startswith("data: ") and line != "data: [DONE]")
            print(f"      [成功] 耗时 {elapsed:.2f}s，收到 {chunks} 个流式分片")
    except requests.RequestException as e:
        print(f"      [失败] {type(e).__name__}: {e}")
        ok = False

    print("=" * 60)
    if ok:
        print(f"[通过] {model} 可用，经理节点模型配置正确 ✔")
        return 0
    print("[未通过] 请检查模型名称与 API Key 额度")
    return 1


if __name__ == "__main__":
    sys.exit(main())
