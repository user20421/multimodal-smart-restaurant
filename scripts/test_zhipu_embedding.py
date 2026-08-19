# -*- coding: utf-8 -*-
"""
智谱 Embedding-3 向量模型连通性测试

从本地环境变量 ZHIPU_API_KEY 读取 API Key，
调用智谱 Embedding-3 模型（512 维）生成文本向量，
验证模型是否可用，并打印测试结果（成功/失败）。

用法:
    python scripts/test_zhipu_embedding.py
"""
import os
import sys
from pathlib import Path

# 被测模型与向量维度
MODEL = "embedding-3"
DIMENSIONS = 512
TEST_TEXTS = ["美味餐厅的招牌水煮鱼非常正宗", "今天天气不错，适合出去吃饭"]


def _get_key(name: str) -> str:
    """从 backend/.env 读取配置（.env 优先，环境变量兜底）"""
    env_file = Path(__file__).resolve().parents[1] / "backend" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip()
    return os.environ.get(name, "")


def main() -> int:
    api_key = _get_key("ZHIPU_API_KEY")
    if not api_key:
        print("[失败] 未在 backend/.env 或环境变量中找到 ZHIPU_API_KEY，请先配置智谱 API Key")
        return 1

    print(f"测试模型: {MODEL} (dimensions={DIMENSIONS})")
    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")
    print("-" * 50)

    try:
        from zhipuai import ZhipuAI
    except ImportError:
        print("[失败] 未安装 zhipuai SDK，请先执行: pip install zhipuai")
        return 1

    try:
        client = ZhipuAI(api_key=api_key)
        response = client.embeddings.create(
            model=MODEL,
            input=TEST_TEXTS,
            dimensions=DIMENSIONS,
        )

        embeddings = response.data
        if not embeddings:
            print("[失败] 接口返回成功，但未包含任何向量数据")
            return 1

        actual_dim = len(embeddings[0].embedding)
        print(f"输入文本数: {len(TEST_TEXTS)}")
        print(f"返回向量数: {len(embeddings)}")
        print(f"向量维度: {actual_dim}")
        print(f"向量样例(前5维): {[round(v, 6) for v in embeddings[0].embedding[:5]]}")
        if hasattr(response, "usage") and response.usage:
            print(f"Token 用量: {response.usage.total_tokens}")
        print("-" * 50)

        if actual_dim != DIMENSIONS:
            print(f"[失败] 向量维度不符，期望 {DIMENSIONS} 维，实际 {actual_dim} 维")
            return 1

        print(f"[成功] {MODEL} 模型调用正常，已获得 {DIMENSIONS} 维向量 ✔")
        return 0

    except Exception as e:
        print("-" * 50)
        print(f"[失败] 调用 {MODEL} 模型出错: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
