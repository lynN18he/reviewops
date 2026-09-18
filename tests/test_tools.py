"""
测试 RAG Tool 与 Chroma metadata filter 的绑定关系。
"""

from langchain_core.documents import Document

from src import tools


class _FakeRetriever:
    def __init__(self, docs):
        self.docs = docs

    def invoke(self, query):
        return self.docs


class _FakeVectorStore:
    def __init__(self, retriever_docs=None, fallback_docs=None):
        self.retriever_docs = retriever_docs or []
        self.fallback_docs = fallback_docs or []
        self.search_kwargs = None
        self.fallback_filter = None

    def as_retriever(self, search_type, search_kwargs):
        self.search_type = search_type
        self.search_kwargs = search_kwargs
        return _FakeRetriever(self.retriever_docs)

    def similarity_search(self, query, k, filter=None):
        self.fallback_filter = filter
        return self.fallback_docs


def test_search_known_issues_applies_jira_metadata_filter(monkeypatch):
    vs = _FakeVectorStore()
    monkeypatch.setattr(tools, "_get_vectorstore", lambda: vs)

    tools.search_known_issues.invoke({"query": "订单同步又失败了"})

    assert vs.search_kwargs["filter"] == {"doc_type": "jira_ticket"}
    assert vs.fallback_filter == {"doc_type": "jira_ticket"}


def test_search_release_notes_applies_release_metadata_filter(monkeypatch):
    vs = _FakeVectorStore()
    monkeypatch.setattr(tools, "_get_vectorstore", lambda: vs)

    tools.search_release_notes.invoke({"query": "昨天发版后白屏"})

    assert vs.search_kwargs["filter"] == {"doc_type": "release_note"}
    assert vs.fallback_filter == {"doc_type": "release_note"}


def test_search_api_docs_and_sop_applies_sop_metadata_filter(monkeypatch):
    vs = _FakeVectorStore()
    monkeypatch.setattr(tools, "_get_vectorstore", lambda: vs)

    tools.search_api_docs_and_sop.invoke({"query": "HMAC validation failed"})

    assert vs.search_kwargs["filter"] == {"doc_type": "SOP"}
    assert vs.fallback_filter == {"doc_type": "SOP"}


def test_unfiltered_search_remains_available_for_broad_fallback(monkeypatch):
    docs = [Document(page_content="通用命中", metadata={"doc_type": "SOP", "doc_id": "SOP-001"})]
    vs = _FakeVectorStore(retriever_docs=docs)
    monkeypatch.setattr(tools, "_get_vectorstore", lambda: vs)

    out = tools._search_chroma("401 错误")

    assert "通用命中" in out
    assert "filter" not in vs.search_kwargs

