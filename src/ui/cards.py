"""
卡片渲染组件模块
封装 RAG 和 Action 卡片的渲染逻辑
"""

import streamlit as st

from src.utils import sanitize_stored_rag_text_for_ui


def _columns_balanced():
    try:
        return st.columns([1, 1], gap="large")
    except TypeError:
        return st.columns([1, 1])


def _info_icon(body: str, icon: str) -> None:
    try:
        st.info(body, icon=icon)
    except TypeError:
        st.info(body)


def _success_icon(body: str, icon: str) -> None:
    try:
        st.success(body, icon=icon)
    except TypeError:
        st.success(body)


def render_ticket_card(rag_result, action_item, batch_idx=0, item_idx=0, show_resolve_button=False, resolve_callback=None):
    """
    单条工单：左栏只读信息用 info/success/markdown；右栏可编辑草稿与操作。
    """
    ticket_id = rag_result.get("ticket_id", f"未知_{item_idx}")
    ticket_content = rag_result.get("ticket_content", "") or ""
    conclusion = sanitize_stored_rag_text_for_ui(
        rag_result.get("conclusion", "❓ 需要人工判断") or "❓ 需要人工判断"
    )
    reason = sanitize_stored_rag_text_for_ui(rag_result.get("reason", "") or "")
    evidence = sanitize_stored_rag_text_for_ui(rag_result.get("evidence", "") or "")

    if "缺陷" in conclusion or "⚠️" in conclusion or "需进一步调查" in conclusion:
        conclusion_type = "系统缺陷"
    elif "用户" in conclusion or "❓" in conclusion or "用户使用问题" in conclusion or "配置" in conclusion:
        conclusion_type = "用户/配置问题"
    elif "✅" in conclusion or "已知局限" in conclusion:
        conclusion_type = "已知局限"
    else:
        conclusion_type = "其他问题"

    _category_header = {
        "系统缺陷": ("🔴", "系统缺陷"),
        "用户/配置问题": ("⚠️", "用户/配置"),
        "已知局限": ("ℹ️", "已知局限"),
        "其他问题": ("🔵", "其他"),
    }
    status_icon, category_label = _category_header.get(conclusion_type, ("🔵", "其他"))

    unique_key = f"case_{batch_idx}_{item_idx}_{ticket_id}"
    action_type = action_item.get("action_type", "Jira Ticket") if action_item else ""
    action_title = action_item.get("title", "") if action_item else ""
    action_content = action_item.get("content", "") if action_item else ""
    priority = action_item.get("priority", "Medium") if action_item else "Medium"
    type_display = {
        "Jira Ticket": "Jira",
        "Email Draft": "邮件草稿",
        "Doc Update": "文档更新",
        "Meeting": "会议",
    }.get(action_type, action_type or "—")

    conclusion_text = conclusion.replace("**结论：**", "").strip() or "—"
    draft_key = f"draft_edit_{unique_key}"

    with st.container(border=True):
        st.markdown(f"### {status_icon} [{category_label}] `{ticket_id}`")

        col_left, col_right = _columns_balanced()

        with col_left:
            st.markdown("**👤 客户原文**")
            _info_icon(ticket_content.strip() if ticket_content.strip() else "（暂无）", "💬")

            st.markdown("**🧠 AI 诊断**")
            st.markdown(f"**归因结论：** {conclusion_text}")
            st.markdown(f"**诊断推理：** {reason if reason else '—'}")

            st.markdown("**📚 知识库依据**")
            ev = str(evidence).strip() if evidence else ""
            if ev:
                _success_icon(ev, "🔍")
            else:
                st.caption("暂无结构化检索依据")

        with col_right:
            st.markdown("**⚙️ 处理建议**")
            if action_item and action_title:
                if action_content:
                    st.markdown(f"**优先级：** {priority} | **动作：** {type_display}")
                    if action_title:
                        st.caption(action_title)
                    st.text_area(
                        label="📝 建议回复草稿 (您可以直接在此修改)",
                        value=action_content,
                        height=300,
                        key=draft_key,
                        help="审阅后可复制或推送。",
                    )
                    c1, c2 = st.columns(2)
                    with c1:
                        if action_type == "Jira Ticket":
                            if st.button(
                                "🚀 推送 Jira",
                                key=f"jira_{unique_key}",
                                type="primary",
                                width="stretch",
                            ):
                                import random

                                jid = f"RO-2025-{random.randint(1000, 9999)}"
                                st.toast(f"Jira 已创建 {jid}", icon="🎉")
                        else:
                            if st.button(
                                "📋 复制草稿",
                                key=f"copy_{unique_key}",
                                width="stretch",
                            ):
                                to_copy = st.session_state.get(draft_key, action_content) or ""
                                _clip = getattr(st, "clipboard", None)
                                if callable(_clip):
                                    try:
                                        _clip(to_copy)
                                        st.toast("已复制", icon="🎉")
                                    except Exception:
                                        st.toast("请框内全选后复制", icon="📋")
                                else:
                                    st.toast("请框内全选后复制", icon="📋")
                    with c2:
                        if show_resolve_button and resolve_callback:
                            if st.button(
                                "✅ 标记已处理",
                                type="primary",
                                key=f"proc_{unique_key}",
                                width="stretch",
                            ):
                                resolve_callback()
                                st.rerun()
                else:
                    st.caption("行动建议生成中…")
            else:
                st.markdown("**优先级：** — | **动作：** —")
                st.caption("暂无自动行动建议。")
                with st.expander("手动创建行动", expanded=False):
                    st.selectbox(
                        "类型",
                        ["Jira Ticket", "Doc Update", "Email Draft", "Meeting"],
                        key=f"manual_action_type_{unique_key}",
                    )
                    st.text_input(
                        "标题",
                        value=f"处理工单 {ticket_id}",
                        key=f"manual_action_title_{unique_key}",
                    )
                    st.text_area(
                        "正文",
                        value=f"用户反馈：{ticket_content[:200] if ticket_content else ''}...",
                        height=100,
                        key=f"manual_action_content_{unique_key}",
                    )
                    if st.button("创建", key=f"manual_action_create_{unique_key}"):
                        st.toast("已创建（演示）", icon="🎉")
