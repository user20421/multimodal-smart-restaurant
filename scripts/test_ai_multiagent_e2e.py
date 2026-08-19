#!/usr/bin/env python3
"""
多智能体图端到端验证

验证 router 分类节点把复杂意图分发给正确的专员 Agent：
- 指代不清 -> unclear 固定话术（不执行任何操作）
- 一句话多菜品加购 -> cart 专员（LLM 多工具调用）
- 菜品咨询 -> knowledge 专员
- 闲聊 -> chitchat 节点（引回餐厅话题）
- 出格请求 -> chitchat 礼貌拒绝
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


def post_json(path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers)
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def chat(token, message, cart):
    r = post_json("/api/v1/ai/chat", {"message": message, "cart": cart}, token=token)
    print(f"  问: {message}\n  答: {r['response'][:100]}")
    return r


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} {detail}")


def main():
    import re
    emoji_re = re.compile(
        "[\U0001f000-\U0001faff\U00002600-\U000027bf\U00002b00-\U00002bff\ufe0f\u200d]"
    )
    replies = []

    username = f"ma_e2e_{int(time.time())}"
    post_json("/api/v1/auth/register", {"username": username, "password": "Test123456", "gender": "unknown"})
    cap = post_json("/api/v1/auth/captcha")
    code = REDIS.get(f"captcha:{cap['captcha_id']}")
    token = post_json("/api/v1/auth/login", {"username": username, "password": "Test123456",
                                             "captcha_id": cap["captcha_id"], "captcha_code": code})["token"]

    menu = post_json("/api/v1/menu", token=token)
    items = menu["items"] if isinstance(menu, dict) else menu
    dish1, dish2 = items[0]["name"], items[1]["name"]

    # 1. 指代不清 -> unclear，不执行任何操作
    r = chat(token, "帮我把刚才那个菜再加一份", [])
    replies.append(r["response"])
    check("指代不清拒绝执行", "一句话" in r["response"] or "说清" in r["response"], r["response"][:100])
    check("指代不清不改购物车", r["cart"] == [], str(r["cart"]))

    # 2. 一句话多菜品 -> cart 专员（复杂加购，fastpath 覆盖不到）
    r = chat(token, f"{dish1}和{dish2}各来两份", [])
    replies.append(r["response"])
    names = {i["name"]: i["quantity"] for i in r["cart"]}
    check("多菜品加购", names.get(dish1) == 2 and names.get(dish2) == 2, str(r["cart"]))
    cart = r["cart"]

    # 3. 菜品咨询 -> knowledge 专员（只读，不改购物车）
    r = chat(token, f"{dish1}辣不辣？", cart)
    replies.append(r["response"])
    check("菜品咨询有回复", len(r["response"]) > 5, r["response"][:50])
    check("咨询不改购物车", r["cart"] == cart, str(r["cart"]))

    # 4. 闲聊 -> chitchat，引回餐厅话题
    r = chat(token, "今天心情真好", cart)
    replies.append(r["response"])
    check("闲聊有回复", len(r["response"]) > 3, r["response"][:50])

    # 5. 出格请求 -> 礼貌拒绝
    r = chat(token, "帮我写一个Python爬虫", cart)
    replies.append(r["response"])
    check("出格请求被礼貌处理", len(r["response"]) > 3, r["response"][:80])

    # 6. 自然语言下单 -> cart 专员（下单归 cart）
    r = chat(token, "帮我把购物车里的菜结算一下吧", cart)
    replies.append(r["response"])
    check("自然语言下单成功", "下单成功" in r["response"], r["response"][:120])
    check("下单后购物车清空", r["cart"] == [], str(r["cart"]))

    # 7. 查询已下单订单 -> order 专员（只读）
    r = chat(token, "我的订单现在什么情况", [])
    replies.append(r["response"])
    check("订单查询有回复", len(r["response"]) > 5, r["response"][:80])

    # 8. 全部回复不含表情符号（提示词 + 出口净化双重保障）
    check("回复均不含表情", all(not emoji_re.search(t) for t in replies),
          str([t[:30] for t in replies if emoji_re.search(t)]))
    print("\n结果: {} 通过, {} 失败".format(PASS, FAIL))
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
