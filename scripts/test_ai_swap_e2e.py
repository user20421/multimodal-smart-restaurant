#!/usr/bin/env python3
"""换菜语义专项验证：整项换 vs 部分换，是否会搞混"""
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
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def chat(token, message, cart):
    r = post_json("/api/v1/ai/chat", {"message": message, "cart": cart}, token=token)
    print(f"  问: {message}")
    print(f"  答: {r['response'][:120]}")
    print(f"  购物车: {[(i['name'], i['quantity']) for i in r['cart']]}")
    return r


def main():
    username = f"swap_e2e_{int(time.time())}"
    post_json("/api/v1/auth/register", {"username": username, "password": "Test123456", "gender": "unknown"})
    cap = post_json("/api/v1/auth/captcha")
    code = REDIS.get(f"captcha:{cap['captcha_id']}")
    token = post_json("/api/v1/auth/login", {"username": username, "password": "Test123456",
                                             "captcha_id": cap["captcha_id"], "captcha_code": code})["token"]

    menu = post_json("/api/v1/menu", token=token)
    items = menu["items"] if isinstance(menu, dict) else menu
    names = [i["name"] for i in items]
    dish_a = next(n for n in names if "宫保鸡丁" in n)
    dish_b = next(n for n in names if "水煮鱼" in n)
    print(f"测试菜品: {dish_a} / {dish_b}")

    # 先加 3 份宫保鸡丁
    r = chat(token, f"来三份{dish_a}", [])
    assert {i["name"]: i["quantity"] for i in r["cart"]} == {dish_a: 3}
    cart = r["cart"]

    # 部分换：两份宫保鸡丁 -> 一份水煮鱼
    r = chat(token, f"把其中两份{dish_a}换成一份{dish_b}", cart)
    got = {i["name"]: i["quantity"] for i in r["cart"]}
    assert got == {dish_a: 1, dish_b: 1}, got
    print("[PASS] 部分换：A剩1 + B有1")
    cart = r["cart"]

    # 整项换：宫保鸡丁 -> 水煮鱼（剩的1份换成1份水煮鱼，合并为2份）
    r = chat(token, f"把{dish_a}换成{dish_b}", cart)
    got = {i["name"]: i["quantity"] for i in r["cart"]}
    assert got == {dish_b: 2}, got
    print("[PASS] 整项换：只剩B，共2份")

    print("换菜语义验证通过，两种情况不会搞混")


if __name__ == "__main__":
    main()
