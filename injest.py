"""
知识库摄入：按 Markdown 标题层级切分 + 结构化 metadata，再写入 ChromaDB。

运行：在项目根执行  python injest.py

环境变量：
  DASHSCOPE_API_KEY — 必需
  EMBEDDING_MODEL — 默认 text-embedding-v3（与 src.config.EmbeddingConfig 一致）
  INJEST_EMBED_BATCH — 每批条数，默认 8（略减小可降低单次 SSL/超时概率）
  INJEST_EMBED_RETRIES — 每批最多重试次数，默认 8
  INJEST_EMBED_RETRY_DELAY_SEC — 退避基数秒，默认 2（实际等待为 基数 * 2^attempt + 抖动）
  INJEST_BATCH_SLEEP_SEC — 批次之间休眠秒数，默认 0.15（缓和连接复用导致的 EOF）
  INJEST_PRINT_DETAIL — 打印样例条数，0 为不打印长正文
  VECTOR_DB_PATH — 未设置时使用仓库根下 chroma_db（见 src.config）
"""

from __future__ import annotations

import os
import random
import re
import shutil
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, List, TypeVar

_REPO_DIR = Path(__file__).resolve().parent

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import Chroma

load_dotenv()

warnings.filterwarnings("ignore", message=".*[Cc]hroma.*deprecated.*", category=DeprecationWarning)

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    import urllib3
except ImportError:
    urllib3 = None  # type: ignore

HEADERS_TO_SPLIT_ON = [
    ("##", "Category"),
    ("###", "Title"),
]

T = TypeVar("T")


def ensure_api_key() -> str:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "未检测到 DASHSCOPE_API_KEY。请在 .env 中配置或 export DASHSCOPE_API_KEY=..."
        )
    return api_key


def _transient_embedding_error(exc: BaseException) -> bool:
    """SSL EOF、连接重置、超时等可重试错误。"""
    if requests is not None and isinstance(
        exc,
        (
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError,
        ),
    ):
        return True
    if urllib3 is not None and isinstance(exc, urllib3.exceptions.HTTPError):
        return True
    msg = str(exc).lower()
    if any(
        x in msg
        for x in (
            "ssl",
            "eof",
            "connection",
            "timeout",
            "max retries",
            "temporarily",
            "refused",
            "reset",
            "broken pipe",
            "unreachable",
        )
    ):
        return True
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause is not None and cause is not exc:
        return _transient_embedding_error(cause)
    return False


def _retry_transient(
    label: str,
    fn: Callable[[], T],
    *,
    max_attempts: int,
    base_delay: float,
) -> T:
    last: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            if not _transient_embedding_error(e) or attempt >= max_attempts - 1:
                raise
            delay = base_delay * (2**attempt) + random.uniform(0, 0.75)
            print(
                f"   ⚠️ {label}：{type(e).__name__}，{delay:.1f}s 后重试 ({attempt + 1}/{max_attempts})…"
            )
            time.sleep(delay)
    assert last is not None
    raise last


def get_embeddings() -> DashScopeEmbeddings:
    from src.config import EmbeddingConfig

    ensure_api_key()
    print("🔌 使用 DashScope Embedding（模型与项目配置一致）…")
    return DashScopeEmbeddings(
        model=EmbeddingConfig.MODEL,
        dashscope_api_key=EmbeddingConfig.get_api_key(),
    )


def _normalize_chroma_metadata(meta: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in meta.items():
        if v is None:
            out[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            out[k] = str(v)
        else:
            out[k] = str(v)
    return out


def enrich_document_metadata(doc: Document) -> Document:
    meta: Dict[str, Any] = dict(doc.metadata)
    category = (meta.get("Category") or "").strip()
    title = (meta.get("Title") or "").strip()
    cat_u = category.upper()

    if not category and not title:
        meta["doc_type"] = "kb_overview"
        meta["doc_id"] = ""
        meta["release_version"] = ""
        meta["release_date"] = ""
        meta["jira_id"] = ""
        return Document(page_content=doc.page_content, metadata=_normalize_chroma_metadata(meta))

    if "SOP" in category or re.search(r"SOP-\d+", title, re.IGNORECASE):
        meta["doc_type"] = "SOP"
        m = re.search(r"SOP-\d+", title, re.IGNORECASE)
        meta["doc_id"] = m.group(0).upper() if m else ""
        meta["release_version"] = ""
        meta["release_date"] = ""
        meta["jira_id"] = ""
    elif "发版" in category or "RELEASE" in cat_u or "Release Notes" in category:
        meta["doc_type"] = "release_note"
        meta["doc_id"] = ""
        vm = re.search(r"\[v[\d.]+\]", title, re.IGNORECASE)
        if vm:
            meta["release_version"] = vm.group(0).strip("[]")
        else:
            vm2 = re.search(r"v[\d.]+", title, re.IGNORECASE)
            meta["release_version"] = vm2.group(0) if vm2 else ""
        dm = re.search(r"\d{4}-\d{2}-\d{2}", title)
        meta["release_date"] = dm.group(0) if dm else ""
        meta["jira_id"] = ""
    elif "已知缺陷" in category or "JIRA" in cat_u or "Jira" in category or "KNOWN" in cat_u:
        meta["doc_type"] = "jira_ticket"
        meta["doc_id"] = ""
        meta["release_version"] = ""
        meta["release_date"] = ""
        jm = re.search(r"JIRA-\d+", title, re.IGNORECASE)
        meta["jira_id"] = jm.group(0).upper() if jm else ""
    else:
        meta["doc_type"] = "unknown"
        meta["doc_id"] = ""
        meta["release_version"] = ""
        meta["release_date"] = ""
        meta["jira_id"] = ""

    return Document(page_content=doc.page_content, metadata=_normalize_chroma_metadata(meta))


def load_and_split_knowledge_markdown(text_path: str) -> List[Document]:
    if not os.path.exists(text_path):
        raise FileNotFoundError(f"找不到知识库文件: {text_path}")

    with open(text_path, encoding="utf-8") as f:
        md_text = f.read()

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=True,
    )
    splits = splitter.split_text(md_text)

    enriched: List[Document] = []
    for d in splits:
        text = (d.page_content or "").strip()
        if not text:
            continue
        enriched.append(enrich_document_metadata(Document(page_content=text, metadata=d.metadata)))
    return enriched


def print_chunks_index(docs: List[Document]) -> None:
    print("\n" + "-" * 60)
    print(f"📑 Chunk 全量索引（共 {len(docs)} 条）")
    print("-" * 60)
    for i, doc in enumerate(docs):
        m = doc.metadata
        dt = m.get("doc_type", "")
        title = (m.get("Title") or "")[:56]
        extra = m.get("doc_id") or m.get("jira_id") or m.get("release_version") or "-"
        print(f"  [{i:2d}] {dt:14s} | key={extra:12s} | {title}")
    print("-" * 60 + "\n")


def print_sample_documents(docs: List[Document], n: int = 3) -> None:
    print("\n" + "=" * 60)
    print(f"📋 校验：前 {min(n, len(docs))} 条 Document")
    print("=" * 60)
    for i, doc in enumerate(docs[:n]):
        print(f"\n--- Document [{i}] ---")
        print("metadata:", doc.metadata)
        preview = doc.page_content[:500] + ("…" if len(doc.page_content) > 500 else "")
        print("page_content:\n", preview)
    print("\n" + "=" * 60 + "\n")


def _warmup_embeddings(embeddings: DashScopeEmbeddings) -> None:
    """先打通 API，再删旧库，避免清空后才发现连不上。"""
    retries = int(os.getenv("INJEST_EMBED_RETRIES", "8"))
    delay = float(os.getenv("INJEST_EMBED_RETRY_DELAY_SEC", "2"))
    print("🔎 预检：向量化 API 连通性（失败则不会删除旧 chroma_db）…")

    def _ping():
        embeddings.embed_documents(["__ingest_connection_check__"])

    _retry_transient("Embedding 预检", _ping, max_attempts=retries, base_delay=delay)
    print("   ✅ API 可用")


def _add_batch_with_retry(vectorstore: Chroma, batch: List[Document]) -> None:
    retries = int(os.getenv("INJEST_EMBED_RETRIES", "8"))
    delay = float(os.getenv("INJEST_EMBED_RETRY_DELAY_SEC", "2"))

    def _do():
        vectorstore.add_documents(batch)

    _retry_transient("向量化写入", _do, max_attempts=retries, base_delay=delay)


def _ingest_chunks_resilient(vectorstore: Chroma, batch: List[Document]) -> None:
    """单批失败则减半拆分，直到单条仍失败则抛出明确错误。"""
    if not batch:
        return
    try:
        _add_batch_with_retry(vectorstore, batch)
    except Exception as e:
        if len(batch) == 1:
            hint = (batch[0].metadata or {}).get("Title") or (batch[0].metadata or {}).get(
                "doc_id"
            ) or "（无标题）"
            raise RuntimeError(
                f"单条 Chunk 在重试与降级后仍失败，请检查网络/代理/VPN 或稍后再试。Chunk: {hint[:80]}"
            ) from e
        mid = max(1, len(batch) // 2)
        _ingest_chunks_resilient(vectorstore, batch[:mid])
        _ingest_chunks_resilient(vectorstore, batch[mid:])


def ingest_documents(
    text_path: str = "saas_knowledge.txt",
    persist_directory: str | None = None,
    skip_print_sample: bool = False,
) -> None:
    print("🚀 构建 RAG 知识库（Markdown 切分 + metadata + Chroma）…")

    if persist_directory is None:
        from src.config import VectorStoreConfig

        persist_directory = VectorStoreConfig.PERSIST_DIRECTORY

    if not os.path.exists(text_path):
        fallback = _REPO_DIR / text_path
        if fallback.is_file():
            text_path = str(fallback)
        else:
            print(f"❌ 找不到文件: {text_path}")
            sys.exit(1)

    print(f"📄 读取: {text_path}")
    chunks = load_and_split_knowledge_markdown(text_path)
    print(f"✅ 切分完成，共 {len(chunks)} 个 Chunk")

    if not chunks:
        print("❌ 切分后无 Chunk，请检查 saas_knowledge.txt 的 ## / ### 结构")
        sys.exit(1)

    if not skip_print_sample:
        print_chunks_index(chunks)
        detail_n = int(os.getenv("INJEST_PRINT_DETAIL", "3"))
        if detail_n > 0:
            print_sample_documents(chunks, n=detail_n)

    print("🔑 检查 API Key …")
    embeddings = get_embeddings()
    _warmup_embeddings(embeddings)

    if os.path.isdir(persist_directory):
        print(f"🗑️ 清空旧向量库: {persist_directory}")
        shutil.rmtree(persist_directory)

    batch_size = int(os.getenv("INJEST_EMBED_BATCH", "8"))
    batch_size = max(1, min(batch_size, len(chunks)))
    sleep_between = float(os.getenv("INJEST_BATCH_SLEEP_SEC", "0.15"))

    print(f"🔢 写入 ChromaDB: {persist_directory}（共 {len(chunks)} 条，每批 ≤{batch_size} 条）")
    vectorstore = Chroma(
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        _ingest_chunks_resilient(vectorstore, batch)
        print(f"   … 已写入 {min(i + len(batch), len(chunks))} / {len(chunks)}")
        if sleep_between > 0 and i + batch_size < len(chunks):
            time.sleep(sleep_between)

    print(f"🎉 完成。知识库: {persist_directory}")
    print("👉 可运行 streamlit / seed_db.py / 工作流使用检索。")


def _print_failure_hint(exc: BaseException) -> None:
    if _transient_embedding_error(exc):
        print(
            "\n💡 多为网络或 TLS 抖动（含公司代理、全局 VPN）。可尝试：换网络、调整代理、"
            "执行 `pip install -U certifi requests urllib3`，或增大环境变量 "
            "INJEST_EMBED_RETRIES / INJEST_EMBED_RETRY_DELAY_SEC 后重试。"
        )


if __name__ == "__main__":
    try:
        ingest_documents()
    except Exception as e:
        print(f"❌ 运行失败：{e}")
        _print_failure_hint(e)
        import traceback

        traceback.print_exc()
        sys.exit(1)
