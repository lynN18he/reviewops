"""
测试知识库切分后的 metadata 归类契约。
"""

from langchain_core.documents import Document

from injest import enrich_document_metadata


def test_enrich_metadata_marks_sop_documents():
    doc = Document(
        page_content="重新授权步骤",
        metadata={"Category": "API / SOP 排查手册", "Title": "SOP-001 HMAC 验签失败"},
    )

    out = enrich_document_metadata(doc)

    assert out.metadata["doc_type"] == "SOP"
    assert out.metadata["doc_id"] == "SOP-001"


def test_enrich_metadata_marks_release_notes():
    doc = Document(
        page_content="修复 PayPal 支付链路",
        metadata={"Category": "发版记录", "Title": "[v2.3.9] 2026-02-15 支付修复"},
    )

    out = enrich_document_metadata(doc)

    assert out.metadata["doc_type"] == "release_note"
    assert out.metadata["release_version"] == "v2.3.9"
    assert out.metadata["release_date"] == "2026-02-15"


def test_enrich_metadata_marks_jira_tickets():
    doc = Document(
        page_content="导出大报表 504",
        metadata={"Category": "已知缺陷库", "Title": "JIRA-1059 报表导出超时"},
    )

    out = enrich_document_metadata(doc)

    assert out.metadata["doc_type"] == "jira_ticket"
    assert out.metadata["jira_id"] == "JIRA-1059"

