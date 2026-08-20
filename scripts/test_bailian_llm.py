# -*- coding: utf-8 -*-
"""
阿里云百炼基础对话模型（模型 A）连通性测试

从 backend/.env 读取 DASHSCOPE_API_KEY 与 BAILIAN_LLM_MODEL（当前 qwen3.7-flash-2026-07-15），
通过百炼 OpenAI 兼容接口调用该模型，
验证模型是否可用，并打印测试结果（成功/失败）、推理耗时与回答内容。

用法:
    python scripts/test_bailian_llm.py
"""
import os
import sys
import time
from pathlib import Path

import requests

# 百炼 OpenAI 兼容接口地址（被测模型运行时从 backend/.env 的 BAILIAN_LLM_MODEL 读取）
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
PROMPT = "用一句话介绍川菜的特点。"


def _get_key(name: str) -> str:
    """读取配置：操作系统环境变量优先；backend/.env 中非占位符的值兜底
    （与 app.ai.config 的 _get_key 语义一致：.env 里的占位符视为未设置）"""
    v = os.environ.get(name, "").strip()
    if v:
        return v
    env_file = Path(__file__).resolve().parents[1] / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                v = line.split("=", 1)[1].strip()
                if v and "your" not in v.lower():  # 占位符视为未设置
                    return v
    return ""


def main() -> int:
    api_key = _get_key("DASHSCOPE_API_KEY")
    if not api_key:
        print("[失败] 未在 backend/.env 或环境变量中找到 DASHSCOPE_API_KEY，请先配置阿里云百炼 API Key")
        return 1

    model = _get_key("BAILIAN_LLM_MODEL")
    if not model:
        print("[失败] 未在 backend/.env 配置 BAILIAN_LLM_MODEL")
        return 1

    print(f"测试模型: {model}")
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")
    print(f"统一提问: {PROMPT}")
    print("-" * 50)

    payload = {
        "model": model,
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
        print(f"[成功] {model} 模型调用正常 ✔")
        return 0

    except requests.RequestException as e:
        print("-" * 50)
        print(f"[失败] 调用 {model} 模型出错: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
