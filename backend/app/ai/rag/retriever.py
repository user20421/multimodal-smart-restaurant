"""
知识检索器（混合检索）

向量检索（Chroma + 智谱 embedding-3 512 维）擅长语义相近的问题，
但对"几点关门"这类包含特定字眼的口语化问题召回不足，
因此叠加一个轻量 BM25 关键词索引（字符二元组，无额外依赖），
两者结果合并后返回，供聊天接口注入到大模型上下文中。

并发说明：检索与 manager 的重建共用一把锁（REBUILD_LOCK），
重建期间的检索请求会短暂阻塞等待，而不是读到写了一半的库。
"""
import math
import re
import threading
from typing import List, Optional

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.ai.rag.embeddings import get_embeddings
from app.ai.rag.loader import VECTORSTORE_DIR, load_documents

# 重建/检索互斥锁：manager 重建时持写锁，检索持读锁等待
REBUILD_LOCK = threading.Lock()

_vectorstore: Optional[Chroma] = None
_bm25: Optional["_Bm25Index"] = None


def _get_vectorstore() -> Chroma:
    """懒加载向量库单例。"""
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Chroma(
            persist_directory=str(VECTORSTORE_DIR),
            embedding_function=get_embeddings(),
        )
    return _vectorstore


def _tokenize(text: str) -> List[str]:
    """中文字符二元组切分（无需 jieba 等额外依赖）。"""
    text = re.sub(r"\s+", "", text)
    if len(text) <= 2:
        return [text] if text else []
    return [text[i:i + 2] for i in range(len(text) - 1)]


class _Bm25Index:
    """轻量 BM25 关键词索引（k1=1.5, b=0.75）。"""

    def __init__(self, docs: List[Document]):
        self.docs = docs
        self.tokens = [_tokenize(d.page_content) for d in docs]
        n = max(len(docs), 1)
        df: dict = {}
        for ts in self.tokens:
            for t in set(ts):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.avgdl = sum(len(ts) for ts in self.tokens) / n

    def search(self, query: str, k: int = 3) -> List[Document]:
        k1, b = 1.5, 0.75
        scores = []
        for i, ts in enumerate(self.tokens):
            if not ts:
                continue
            tf: dict = {}
            for t in ts:
                tf[t] = tf.get(t, 0) + 1
            dl = len(ts)
            s = 0.0
            for t in _tokenize(query):
                f = tf.get(t)
                if not f:
                    continue
                s += self.idf.get(t, 0.0) * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self.avgdl))
            if s > 0:
                scores.append((s, i))
        scores.sort(key=lambda x: x[0], reverse=True)
        return [self.docs[i] for _, i in scores[:k]]


def _get_bm25() -> _Bm25Index:
    """懒加载 BM25 索引单例（从知识文档构建，与向量库同源）。"""
    global _bm25
    if _bm25 is None:
        _bm25 = _Bm25Index(load_documents())
    return _bm25


def reset() -> None:
    """清空缓存的单例（向量库重建后由 manager 调用）。"""
    global _vectorstore, _bm25
    _vectorstore = None
    _bm25 = None


def search(query: str, k: int = 5) -> List[Document]:
    """混合检索：BM25 关键词命中优先，合并向量检索结果，去重后返回。

    持锁执行：若恰逢知识库重建，本调用会阻塞等待重建完成后再检索，
    保证不会读到写了一半的库（用户侧表现为回答略慢几秒）。
    """
    if not query.strip():
        return []

    with REBUILD_LOCK:
        keyword_hits = _get_bm25().search(query, k=3)
        vector_hits = _get_vectorstore().similarity_search(query, k=k)

    merged: List[Document] = []
    seen = set()
    for doc in keyword_hits + vector_hits:
        if doc.page_content not in seen:
            seen.add(doc.page_content)
            merged.append(doc)
    return merged[: k + 2]


def get_context(query: str, k: int = 5) -> str:
    """检索并拼接为可注入提示词的上下文文本；无结果时返回空串。"""
    docs = search(query, k=k)
    if not docs:
        return ""
    blocks = [
        f"【{d.metadata.get('category_name', '资料')}】{d.page_content.strip()}"
        for d in docs
    ]
    return "\n\n".join(blocks)
