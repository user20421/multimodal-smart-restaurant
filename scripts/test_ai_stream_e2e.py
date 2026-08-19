#!/usr/bin/env python3
"""SSE 流式聊天快速验证：L1 快速路 + L2 Agent（含 status 事件）"""
import json
import sys
import time
import urllib.request

import redis

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://127.0.0.1:8000"
REDIS = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)


def post_json(path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=90).read())


def stream_chat(token, message, cart):
    req = urllib.request.Request(
        f"{BASE}/api/v1/ai/chat/stream",
        data=json.dumps({"message": message, "cart": cart}).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {token}",
        },
    )
    events = []
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def main():
    username = f"sse_e2e_{int(time.time())}"
    post_json("/api/v1/auth/register", {"username": username, "password": "Test123456", "gender": "unknown"})
    cap = post_json("/api/v1/auth/captcha")
    code = REDIS.get(f"captcha:{cap['captcha_id']}")
    login = post_json("/api/v1/auth/login", {"username": username, "password": "Test123456",
                                             "captcha_id": cap["captcha_id"], "captcha_code": code})
    token = login["token"]

    # L1 快速路（流式打字机，用真实菜单菜品）
    menu = post_json("/api/v1/menu", token=token)
    items = menu["items"] if isinstance(menu, dict) else menu
    dish = items[0]["name"]
    evs = stream_chat(token, f"来两份{dish}", [])
    types = [e["type"] for e in evs]
    text = "".join(e.get("content", "") for e in evs if e["type"] == "text")
    done = next(e for e in evs if e["type"] == "done")
    assert types[0] == "text" and types[-1] == "done", types
    assert dish in text, text
    assert any(i.get("name") == dish and i.get("quantity") == 2 for i in done["cart"]), done
    print(f"[PASS] SSE 快速路: '{text[:40]}' cart={done['cart']}")

    # L2 Agent（闲聊，无工具）
    evs = stream_chat(token, "你好呀，今天心情不错", done["cart"])
    types = set(e["type"] for e in evs)
    text = "".join(e.get("content", "") for e in evs if e["type"] == "text")
    assert "text" in types and "done" in types, types
    assert text.strip(), "闲聊回复为空"
    print(f"[PASS] SSE Agent 闲聊: '{text[:60]}'")

    # L2 Agent（查订单，应出现 status 事件）
    evs = stream_chat(token, "帮我查一下我最近三天的订单", done["cart"])
    types = [e["type"] for e in evs]
    text = "".join(e.get("content", "") for e in evs if e["type"] == "text")
    has_status = "status" in types
    print(f"[{'PASS' if text.strip() else 'FAIL'}] SSE Agent 订单查询: status事件={has_status}, 回复='{text[:80]}'")

    print("SSE 验证完成")


if __name__ == "__main__":
    main()
