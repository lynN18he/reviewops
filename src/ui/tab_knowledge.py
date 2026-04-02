"""
知识资产管理：展示喂给 Agent 的静态知识原文，预留上传与向量化入口（Demo Mock）。
"""

from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

# 相对仓库根目录（Streamlit 工作目录一般为项目根）
KNOWLEDGE_FILENAME = "saas_knowledge.txt"


def _knowledge_path() -> Path:
    p = Path(KNOWLEDGE_FILENAME)
    if p.is_file():
        return p.resolve()
    # 从包内回退（例如从其他 cwd 启动）
    root = Path(__file__).resolve().parents[2] / KNOWLEDGE_FILENAME
    return root.resolve()


def render_page_knowledge_assets() -> None:
    st.markdown("## 📚 知识资产管理")
    st.caption("以下为 RAG / Tool 检索所用的知识原文，便于 Demo 时打破黑盒、可追溯审计。")

    path = _knowledge_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        text = f"（无法读取文件: {e}）"

    st.markdown("### 知识库原文")
    st.text_area(
        "知识库正文",
        value=text,
        height=500,
        disabled=True,
        key="knowledge_assets_view_body",
        label_visibility="collapsed",
    )
    st.caption(f"当前文件：`{path}`")

    st.markdown('<div class="ro-section-gap" aria-hidden="true"></div>', unsafe_allow_html=True)
    st.markdown("### 更新与索引（极客入口）")
    st.file_uploader(
        "上传新知识库（TXT / Markdown，生产流将校验后落盘）",
        type=["txt", "md", "markdown"],
        key="knowledge_assets_uploader",
    )
    if st.button(
        "🔄 同步并重建向量引擎 (Sync to Vector DB)",
        type="primary",
        key="knowledge_assets_sync_btn",
    ):
        st.info("数据切片与向量化构建中…（当前为 Demo Mock，未写入磁盘与向量库）")
        time.sleep(2)
        st.success("Mock 完成：生产环境将接入切片脚本 + Chroma / Embedding 重建。")
        st.toast("向量索引构建（模拟）已完成", icon="🧬")
