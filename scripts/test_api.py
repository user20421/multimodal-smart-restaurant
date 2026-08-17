#!/usr/bin/env python3
"""
API Key 有效性测试脚本（独立可执行，不依赖项目其他文件）
测试本地环境变量中的以下密钥是否可以正常访问对应平台：
  - DASHSCOPE_API_KEY  -> 阿里云百炼平台
  - ZHIPU_API_KEY      -> 智谱 AI 平台

使用方法：
  1. 确保已设置环境变量 DASHSCOPE_API_KEY 和/或 ZHIPU_API_KEY
  2. 直接运行: python scripts/test_api.py
"""

import os
import sys
import json

# 修复 Windows 控制台中文输出乱码
if sys.platform == "win32":
    os.system("chcp 65001 >nul")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m"


def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m"


def _yellow(text: str) -> str:
    return f"\033[93m{text}\033[0m"


def _http_post(url: str, headers: dict, payload: dict, timeout: int = 30):
    """发送 POST 请求，优先使用 requests，回退到 urllib。"""
    try:
        import requests
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        return response.status_code, response.text
    except ImportError:
        pass

    try:
        import urllib.request
        import urllib.error
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={**headers, "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")


def test_zhipu(api_key: str) -> bool:
    """测试智谱 AI API Key 是否有效。"""
    print("\n[智谱 AI 测试开始]")
    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "glm-4.5-air",
        "messages": [{"role": "user", "content": "你好"}],
        "max_tokens": 10,
    }

    try:
        status, body = _http_post(url, headers, payload, timeout=30)
        data = json.loads(body) if body else {}

        if status == 200:
            print(_green("[OK] 智谱 API Key 有效"))
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                print(_green(f"[OK] 模型响应: {content[:80]}..." if len(content) > 80 else f"[OK] 模型响应: {content}"))
            return True

        error_msg = data.get("error", {}).get("message", body[:200])
        print(_red(f"[FAIL] 智谱 API 请求失败 (HTTP {status}): {error_msg}"))
        return False

    except Exception as e:
        print(_red(f"[FAIL] 智谱 API 调用异常: {e}"))
        return False


def test_dashscope(api_key: str) -> bool:
    """测试阿里云百炼 API Key 是否有效（使用 OpenAI 兼容接口）。"""
    print("\n[阿里云百炼 测试开始]")
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "qwen3.7-plus",
        "messages": [{"role": "user", "content": "你好"}],
        "max_tokens": 10,
    }

    try:
        status, body = _http_post(url, headers, payload, timeout=30)
        data = json.loads(body) if body else {}

        if status == 200:
            print(_green("[OK] 百炼 API Key 有效"))
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                print(_green(f"[OK] 模型响应: {content[:80]}..." if len(content) > 80 else f"[OK] 模型响应: {content}"))
            return True

        error_msg = data.get("error", {}).get("message", body[:200])
        print(_red(f"[FAIL] 百炼 API 请求失败 (HTTP {status}): {error_msg}"))
        return False

    except Exception as e:
        print(_red(f"[FAIL] 百炼 API 调用异常: {e}"))
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("API Key 有效性测试")
    print("=" * 50)

    dashscope_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    zhipu_key = os.getenv("ZHIPU_API_KEY", "").strip()

    results = {}

    if zhipu_key:
        results["ZHIPU_API_KEY"] = test_zhipu(zhipu_key)
    else:
        print(_yellow("\n[跳过] 未检测到环境变量 ZHIPU_API_KEY"))
        results["ZHIPU_API_KEY"] = None

    if dashscope_key:
        results["DASHSCOPE_API_KEY"] = test_dashscope(dashscope_key)
    else:
        print(_yellow("\n[跳过] 未检测到环境变量 DASHSCOPE_API_KEY"))
        results["DASHSCOPE_API_KEY"] = None

    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)

    all_ok = True
    for name, ok in results.items():
        if ok is None:
            status = _yellow("未配置")
        elif ok:
            status = _green("通过")
        else:
            status = _red("失败")
            all_ok = False
        print(f"{name:22s} {status}")

    if all_ok and all(v is True for v in results.values()):
        print(_green("\n所有已配置 API Key 均有效"))
        sys.exit(0)
    elif any(v is False for v in results.values()):
        print(_red("\n部分 API Key 测试失败"))
        sys.exit(1)
    else:
        print(_yellow("\n未配置任何 API Key，无法完成测试"))
        sys.exit(2)
