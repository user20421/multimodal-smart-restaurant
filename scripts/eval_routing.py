# -*- coding: utf-8 -*-
"""
路由 + L1 快速路批量评测脚本（基于 scripts/eval_data.py 的 554 条标注数据）

两种模式：
  --mode l1     只评 L1 正则快速路：直连数据库跑 fastpath.try_handle，
                检查"该拦的拦住（reply 非 None）、该放的放行（reply 为 None）"。
                下单类用例使用空购物车预设，L1 返回"购物车是空的"提示即算命中，
                不会真实写订单。不调 LLM，零成本。
  --mode router 只评 L2 意图分类节点：对每条用例调分类模型（temperature=0），
                检查输出标签是否落在该用例的可接受路由集合内。并发 6 路。
  --mode all    先 l1 后 router。

可选过滤：
  --level S/M/H/X   只跑指定难度
  --route cart/...  只跑主标签为指定路由的用例
  --model NAME      评测用模型（默认读 backend/.env 的 BAILIAN_LLM_MODEL；
                    生产模型额度紧张时可指定同代有额度的模型，如 qwen3.7-max-2026-06-08，
                    提示词结论可迁移回生产模型，不影响 .env 配置）

用法：
    python scripts/eval_routing.py --mode l1
    python scripts/eval_routing.py --mode router
    python scripts/eval_routing.py --mode router --model qwen3.7-max-2026-06-08
"""
import argparse
import asyncio
import copy
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.ai import config  # noqa: E402
from app.ai.agent.context import AgentContext  # noqa: E402
from app.ai.agent.fastpath import try_handle  # noqa: E402
from app.ai.agent.graph import _parse_route  # noqa: E402
from app.ai.agent.prompts import ROUTER_PROMPT  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402
from eval_data import CASES, DEFAULT_CART, normalize  # noqa: E402

ALL_ROUTES = ("cart", "order", "knowledge", "chitchat", "manager", "unclear")


def load_cases(level: str | None, route: str | None) -> list[dict]:
    cases = [normalize(c) for c in CASES]
    if level:
        cases = [c for c in cases if c["level"] == level]
    if route:
        wanted = set(route.split(","))
        # 主标签用 sorted 序（与 report 混淆矩阵一致）；
        # 不可用 next(iter(set))——set 迭代序随 PYTHONHASHSEED 跨进程漂移
        cases = [c for c in cases if sorted(c["routes"])[0] in wanted]
    return cases


# ============================================================
# L1 评测
# ============================================================

async def _run_one_l1(case: dict) -> tuple[bool, str]:
    cart = [] if case["cart"] == "empty" else copy.deepcopy(DEFAULT_CART)
    async with AsyncSessionLocal() as db:
        ctx = AgentContext(db=db, user_id=1, message=case["q"], cart=cart)
        reply = await try_handle(ctx, case["q"])
    hit = reply is not None
    ok = hit == case["l1"]
    detail = "" if ok else f"L1{'拦截' if hit else '放行'}，期望{'拦截' if case['l1'] else '放行'}"
    return ok, detail


async def eval_l1(cases: list[dict]) -> list[dict]:
    results = []
    for case in cases:
        try:
            ok, detail = await _run_one_l1(case)
        except Exception as e:
            ok, detail = False, f"异常 {type(e).__name__}: {e}"
        results.append({**case, "ok": ok, "detail": detail})
    return results


# ============================================================
# Router 评测
# ============================================================

def _classify(message: str, model: str) -> str:
    resp = requests.post(
        f"{config.BAILIAN_BASE_URL}/chat/completions",
        json={
            "model": model,
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
    return _parse_route(raw)


def eval_router(cases: list[dict], model: str, workers: int = 6) -> list[dict]:
    def run(case: dict) -> dict:
        for attempt in range(2):
            try:
                actual = _classify(case["q"], model)
                return {**case, "actual": actual, "ok": actual in case["routes"]}
            except Exception:
                if attempt == 1:
                    return {**case, "actual": "<error>", "ok": False}
                time.sleep(2)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, cases))


# ============================================================
# 报告
# ============================================================

def report(results: list[dict], mode: str) -> bool:
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    print("=" * 78)
    print(f"[{mode}] 总体: {passed}/{total} 通过（{passed / total * 100:.1f}%）")

    by_level = defaultdict(lambda: [0, 0])
    for r in results:
        by_level[r["level"]][0] += r["ok"]
        by_level[r["level"]][1] += 1
    for lv in ("S", "M", "H", "X"):
        if lv in by_level:
            p, t = by_level[lv]
            print(f"  难度 {lv}: {p}/{t}（{p / t * 100:.1f}%）")

    if mode == "router":
        matrix = defaultdict(Counter)
        for r in results:
            main_label = sorted(r["routes"])[0]
            matrix[main_label][r["actual"]] += 1
        print("-" * 78)
        print("混淆（期望主标签 -> 实际分布）：")
        for label in ALL_ROUTES:
            if label in matrix:
                dist = ", ".join(f"{k}:{v}" for k, v in matrix[label].most_common())
                print(f"  {label:<10} -> {dist}")

    fails = [r for r in results if not r["ok"]]
    if fails:
        print("-" * 78)
        print(f"失败明细（{len(fails)} 条）：")
        for r in fails:
            if mode == "l1":
                print(f"  [{r['level']}] {r['q']} | {r['note']} | {r['detail']}")
            else:
                expect = "/".join(sorted(r["routes"]))
                print(f"  [{r['level']}] {r['q']} | {r['note']} | 期望 {expect} 实际 {r['actual']}")
    print("=" * 78)
    return passed == total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["l1", "router", "all"], default="all")
    parser.add_argument("--level", choices=["S", "M", "H", "X"], default=None)
    parser.add_argument("--route", default=None,
                        help="主标签过滤，支持逗号分隔多个（如 cart,order）")
    parser.add_argument("--model", default=None,
                        help="评测用模型，默认读配置 BAILIAN_LLM_MODEL")
    args = parser.parse_args()

    cases = load_cases(args.level, args.route)
    print(f"用例总数: {len(cases)}（数据集原始 {len(CASES)} 条）")

    ok_all = True
    if args.mode in ("l1", "all"):
        results = asyncio.run(eval_l1(cases))
        ok_all &= report(results, "l1")
    if args.mode in ("router", "all"):
        model = args.model or config.BAILIAN_LLM_MODEL
        if not config.BAILIAN_API_KEY or not model:
            print("[失败] 未配置 DASHSCOPE_API_KEY 或 BAILIAN_LLM_MODEL")
            return 1
        tag = "（--model 指定）" if args.model else "（.env 配置）"
        print(f"分类模型: {model} {tag}")
        t0 = time.time()
        results = eval_router(cases, model)
        print(f"router 评测耗时 {time.time() - t0:.0f}s")
        ok_all &= report(results, "router")

    print("[全部通过]" if ok_all else "[存在偏差] 见上方失败明细")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
