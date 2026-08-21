# -*- coding: utf-8 -*-
"""
单句路由分类检查（微观调试用，每句只调用分类模型 1 次）:

    python scripts/test_router_one.py "来两份宫爆鸡丁和一份宫保鸡丁" [期望标签]
"""
import sys
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.ai import config  # noqa: E402
from app.ai.agent.graph import _parse_route  # noqa: E402
from app.ai.agent.prompts import ROUTER_PROMPT  # noqa: E402


def classify(message: str) -> str:
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
    return _parse_route(raw)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    sentence = sys.argv[1]
    expected = sys.argv[2] if len(sys.argv) > 2 else None
    route = classify(sentence)
    print(f"{sentence} -> {route}")
    if expected:
        ok = route == expected
        print("[PASS]" if ok else f"[FAIL] 期望 {expected}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
