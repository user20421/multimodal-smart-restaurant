"""
知识库加载与向量库构建

读取 rag/data/ 下的 Markdown 文档（按目录区分类别），
使用智谱 embedding-3（512 维）向量化后存入 Chroma 向量库。

重建向量库：
    cd backend
    python -m app.ai.rag.loader
"""
from pathlib import Path
from typing import List

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.ai.rag.embeddings import get_embeddings

RAG_DIR = Path(__file__).resolve().parent
DATA_DIR = RAG_DIR / "data"
VECTORSTORE_DIR = RAG_DIR / "vectorstore"

# 数据目录名 -> 类别中文名（存入 metadata，便于检索过滤）
CATEGORY_NAMES = {
    "store": "店铺信息",
    "dishes": "菜品介绍",
    "faq": "常见问题",
    "policy": "服务政策",
}


def _split_markdown(text: str) -> List[str]:
    """按二级标题（## ）切分 Markdown，为每个分块补上一级标题作为上下文。

    无二级标题的文档（如菜品介绍）整体作为一个块返回。
    """
    lines = text.split("\n")
    title = ""
    chunks: List[str] = []
    current: List[str] = []

    for line in lines:
        if line.startswith("# ") and not title:
            title = line.lstrip("# ").strip()
        if line.startswith("## "):
            if current:
                chunks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current).strip())

    chunks = [c for c in chunks if c]
    if len(chunks) <= 1:
        return [text.strip()]
    # 为每个分块补上文档标题，保证检索时语义完整
    result = [c if not title or c.startswith(f"# {title}") else f"# {title}\n\n{c}" for c in chunks]
    # 过滤掉除标题外几乎无实质内容的块（纯标题块的向量过于泛化，会污染检索结果）
    return [c for c in result if len(c.replace(f"# {title}", "").strip()) >= 10]


def load_documents() -> List[Document]:
    """加载 data/ 下全部 Markdown 文档，按二级标题切分为知识块。"""
    docs: List[Document] = []
    for md_file in sorted(DATA_DIR.rglob("*.md")):
        category = md_file.parent.name
        text = md_file.read_text(encoding="utf-8")
        for chunk in _split_markdown(text):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={
                        "category": category,
                        "category_name": CATEGORY_NAMES.get(category, category),
                        "source": md_file.name,
                    },
                )
            )
    return docs


def build_vectorstore() -> Chroma:
    """全量重建向量库并持久化到 vectorstore/。

    注意：不能 rmtree 删除目录——运行中的 Chroma 实例持有 chroma.sqlite3
    文件句柄，Windows 下删文件会报 WinError 32。改为删除旧 collection
    再重建，等效于全量重建且无文件锁问题。
    """
    docs = load_documents()
    if not docs:
        raise RuntimeError(f"知识库为空，请先在 {DATA_DIR} 下放置 Markdown 文档")

    embeddings = get_embeddings()

    if _vectorstore_exists():
        try:
            existing = Chroma(
                persist_directory=str(VECTORSTORE_DIR),
                embedding_function=embeddings,
            )
            existing.delete_collection()
        except Exception:
            pass  # 集合不存在等情况忽略，from_documents 会新建

    vectorstore = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        persist_directory=str(VECTORSTORE_DIR),
    )
    return vectorstore


def _vectorstore_exists() -> bool:
    return VECTORSTORE_DIR.exists() and any(VECTORSTORE_DIR.iterdir())


if __name__ == "__main__":
    vs = build_vectorstore()
    print(f"向量库构建完成，共 {len(load_documents())} 个知识块，存储于 {VECTORSTORE_DIR}")
