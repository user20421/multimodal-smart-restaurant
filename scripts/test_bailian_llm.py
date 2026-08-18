# -*- coding: utf-8 -*-
"""
阿里云百炼 DeepSeek 大语言模型连通性测试

从本地环境变量 DASHSCOPE_API_KEY 读取 API Key，
通过百炼 OpenAI 兼容接口调用 deepseek-v4-flash-0731 模型，
验证模型是否可用，并打印测试结果（成功/失败）、推理耗时与回答内容。

用法:
    python scripts/test_bailian_llm.py
"""
import os
import sys
import time

import requests

# 被测模型与百炼 OpenAI 兼容接口地址
MODEL = "deepseek-v4-flash-0731"
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
PROMPT = "用一句话介绍川菜的特点。"


def main() -> int:
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        print("[失败] 未找到环境变量 DASHSCOPE_API_KEY，请先设置阿里云百炼 API Key")
        return 1

    print(f"测试模型: {MODEL}")
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")
    print(f"统一提问: {PROMPT}")
    print("-" * 50)

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        start = time.perf_counter()
        resp = requests.post(API_URL, json=payload, headers=headers, timeout=120)
        elapsed = time.perf_counter() - start

        if resp.status_code != 200:
            print(f"[失败] HTTP {resp.status_code}: {resp.text[:500]}")
            return 1

        data = resp.json()
        answer = (data["choices"][0]["message"].get("content") or "").strip()
        if not answer:
            print("[失败] 接口返回成功，但模型未输出任何内容")
            return 1

        usage = data.get("usage") or {}
        print(f"推理耗时: {elapsed:.2f} 秒")
        print(f"Token 用量: {usage.get('total_tokens', '-')}"
              f"（输入 {usage.get('prompt_tokens', '-')} / 输出 {usage.get('completion_tokens', '-')}）")
        print(f"模型回答: {answer}")
        print("-" * 50)
        print(f"[成功] {MODEL} 模型调用正常 ✔")
        return 0

    except requests.RequestException as e:
        print("-" * 50)
        print(f"[失败] 调用 {MODEL} 模型出错: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
