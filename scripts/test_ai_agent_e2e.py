#!/usr/bin/env python3
"""
AI 智能聊天 Agent 端到端验证脚本

验证分级管线（L1 正则快速路 + 下单/订单查询）：
注册临时用户 -> 验证码登录（从 Redis 读答案）-> 通过 /api/v1/ai/chat 完成：
加菜 -> 换菜 -> 查看购物车 -> 下单 -> 最近订单 / 今日订单。

前置条件：后端已启动（127.0.0.1:8000），MySQL/Redis/MongoDB 容器运行中。
"""
import json
import sys
import time
import urllib.request

import redis

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"
REDIS = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

PASS, FAIL = 0, 0


def request_json(path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=90)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} {detail}")


def login_with_captcha(username, password):
    _, cap = request_json("/api/v1/auth/captcha")
    code = REDIS.get(f"captcha:{cap['captcha_id']}")
    status, result = request_json(
        "/api/v1/auth/login",
        {
            "username": username,
            "password": password,
            "captcha_id": cap["captcha_id"],
            "captcha_code": code,
        },
    )
    assert status == 200, f"登录失败: {status} {result}"
    return result["token"]


def chat(token, message, cart):
    status, result = request_json(
        "/api/v1/ai/chat",
        {"message": message, "cart": cart},
        token=token,
    )
    assert status == 200, f"聊天接口失败: {status} {result}"
    print(f"  问: {message}\n  答: {result['response'][:120]}")
    return result


def main():
    status, _ = request_json("/health")
    assert status == 200, "后端未就绪"

    # 1. 注册 + 登录
    username = f"ai_e2e_{int(time.time())}"
    password = "Test123456"
    status, result = request_json(
        "/api/v1/auth/register",
        {"username": username, "password": password, "gender": "unknown"},
    )
    assert status in (200, 201), f"注册失败: {status} {result}"
    token = login_with_captcha(username, password)
    print(f"临时用户 {username} 注册并登录成功")

    # 2. 获取真实菜单，挑两道菜
    status, menu = request_json("/api/v1/menu", token=token)
    items = menu["items"] if isinstance(menu, dict) else menu
    dish1, dish2 = items[0]["name"], items[1]["name"]
    price2 = items[1]["price"]
    print(f"测试菜品: {dish1} / {dish2}")

    # 3. 加菜（L1 快速路）
    r = chat(token, f"来三份{dish1}", [])
    check("加菜进入购物车", any(i["name"] == dish1 and i["quantity"] == 3 for i in r["cart"]), str(r["cart"]))
    cart = r["cart"]

    # 4. 换菜（复合：先减再加）
    r = chat(token, f"把{dish1}换成两份{dish2}", cart)
    check(
        "换菜成功",
        len(r["cart"]) == 1 and r["cart"][0]["name"] == dish2 and r["cart"][0]["quantity"] == 2,
        str(r["cart"]),
    )
    cart = r["cart"]

    # 5. 查看购物车
    r = chat(token, "看看购物车", cart)
    check("查看购物车", dish2 in r["response"], r["response"][:100])

    # 6. 下单
    r = chat(token, "确认下单", cart)
    check("下单成功", "下单成功" in r["response"], r["response"][:150])
    check("下单后购物车清空", r["cart"] == [], str(r["cart"]))

    # 7. 最近订单
    r = chat(token, "最近1条订单", [])
    check("最近订单包含刚下的菜", dish2 in r["response"], r["response"][:150])

    # 8. 今日订单
    r = chat(token, "今天的订单", [])
    check("今日订单包含刚下的菜", dish2 in r["response"], r["response"][:150])

    # 9. 不存在的菜 -> 让位给 Agent（LLM），不应静默改购物车
    r = chat(token, "来一份佛跳墙", [])
    check("未知菜品不污染购物车", r["cart"] == [], str(r["cart"]))

    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
