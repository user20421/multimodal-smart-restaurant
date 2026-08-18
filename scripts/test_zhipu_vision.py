# -*- coding: utf-8 -*-
"""
智谱视觉模型连通性 + 对比测试

从本地环境变量 ZHIPU_API_KEY 读取 API Key，
使用本地图片 scripts/扩散模型.jpg，调用
GLM-4V-Flash 视觉模型进行图片理解，
对比两个模型的回答内容与推理耗时，
验证模型是否可用，并打印测试结果（成功/失败）。

用法:
    python scripts/test_zhipu_vision.py
"""
import base64
import os
import sys
import time
from pathlib import Path

# 待测试的视觉模型
MODELS = ["glm-4v-flash"]
# 测试图片（与本脚本同目录）
IMAGE_PATH = Path(__file__).resolve().parent / "扩散模型.jpg"
PROMPT = "简单描述图片的内容"
# 思考模式开关：GLM-4.6V 系列默认开启思考模式（更慢），此处关闭以加快响应
THINKING = {"type": "disabled"}


def _build_messages(image_b64: str) -> list:
    """构造统一的图文消息"""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                },
                {"type": "text", "text": PROMPT},
            ],
        }
    ]


def load_image_b64(path: Path) -> str:
    """读取本地图片并返回 base64 编码"""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def test_model(client, model: str, image_b64: str) -> dict:
    """调用单个视觉模型，返回 {ok, answer, elapsed, tokens, error}"""
    result = {"model": model, "ok": False, "answer": "", "elapsed": 0.0, "tokens": None, "error": "", "thinking": True}
    try:
        start = time.perf_counter()
        try:
            # 优先使用非思考模式；旧模型（如 glm-4v-flash）不支持 thinking 参数时自动回退
            response = client.chat.completions.create(
                model=model,
                thinking=THINKING,
                messages=_build_messages(image_b64),
            )
        except Exception as e:
            if "thinking" not in str(e).lower():
                raise
            result["thinking"] = False
            start = time.perf_counter()
            response = client.chat.completions.create(
                model=model,
                messages=_build_messages(image_b64),
            )
        result["elapsed"] = time.perf_counter() - start

        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            result["error"] = "接口返回成功，但模型未输出任何内容"
            return result

        result["ok"] = True
        result["answer"] = answer
        if hasattr(response, "usage") and response.usage:
            result["tokens"] = response.usage.total_tokens
    except Exception as e:
        result["elapsed"] = time.perf_counter() - start if result["elapsed"] == 0.0 else result["elapsed"]
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def main() -> int:
    api_key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if not api_key:
        print("[失败] 未找到环境变量 ZHIPU_API_KEY，请先设置智谱 API Key")
        return 1

    if not IMAGE_PATH.exists():
        print(f"[失败] 未找到测试图片: {IMAGE_PATH}")
        return 1

    print(f"测试模型: {' vs '.join(MODELS)}")
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")
    print(f"测试图片: {IMAGE_PATH.name} ({IMAGE_PATH.stat().st_size / 1024:.1f} KB)")
    print(f"统一提问: {PROMPT}")
    print(f"思考模式: {THINKING['type']}")
    print("=" * 60)

    try:
        from zhipuai import ZhipuAI
    except ImportError:
        print("[失败] 未安装 zhipuai SDK，请先执行: pip install zhipuai")
        return 1

    image_b64 = load_image_b64(IMAGE_PATH)
    client = ZhipuAI(api_key=api_key)

    results = []
    for model in MODELS:
        print(f"\n>>> 正在调用 {model} ...")
        r = test_model(client, model, image_b64)
        results.append(r)
        print("-" * 60)
        print(f"模型: {r['model']}")
        if r["ok"]:
            print(f"状态: [成功] ✔")
            print(f"思考模式: {'disabled' if r['thinking'] else '不支持/未设置'}")
            print(f"推理耗时: {r['elapsed']:.2f} 秒")
            if r["tokens"] is not None:
                print(f"Token 用量: {r['tokens']}")
            print(f"模型回答:\n{r['answer']}")
        else:
            print(f"状态: [失败] {r['error']}")
            print(f"耗时: {r['elapsed']:.2f} 秒")

    # 对比总结
    print("\n" + "=" * 60)
    print("对比总结")
    print("=" * 60)
    ok_results = [r for r in results if r["ok"]]
    for r in results:
        status = "成功" if r["ok"] else "失败"
        tokens = str(r["tokens"]) if r["tokens"] is not None else "-"
        thinking = "非思考" if r["thinking"] else "默认"
        print(f"{r['model']:<20} 状态: {status}   耗时: {r['elapsed']:>6.2f}s   Token: {tokens:<6} 模式: {thinking}")

    if len(ok_results) >= 2:
        sorted_results = sorted(ok_results, key=lambda r: r["elapsed"])
        fastest, slowest = sorted_results[0], sorted_results[-1]
        print("\n推理速度排名:")
        for i, r in enumerate(sorted_results, 1):
            speedup = r["elapsed"] / fastest["elapsed"] if fastest["elapsed"] > 0 else 1.0
            print(f"  {i}. {r['model']:<20} {r['elapsed']:>6.2f}s（{speedup:.2f}x）   回答 {len(r['answer'])} 字")
        if len(ok_results) > 2:
            print(f"最快: {fastest['model']}，最慢: {slowest['model']}，相差 "
                  f"{slowest['elapsed'] - fastest['elapsed']:.2f}s")

    if len(ok_results) == len(results):
        print(f"\n[成功] 全部 {len(results)} 个视觉模型均调用正常 ✔")
        return 0
    elif ok_results:
        failed = [r['model'] for r in results if not r['ok']]
        print(f"\n[部分成功] {len(ok_results)}/{len(results)} 个模型调用正常，失败: {', '.join(failed)}")
        return 1
    else:
        print("\n[失败] 所有视觉模型均调用失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
