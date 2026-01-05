"""
卡片渲染组件模块
封装 RAG 和 Action 卡片的渲染逻辑
"""

import streamlit as st


def render_incident_card(rag_result, action_item, batch_idx=0, item_idx=0):
    """
    成组渲染单个 Case：包含 RAG 归因分析 + 对应的行动建议
    采用 Case-Based 布局，形成完整的证据链闭环
    
    Args:
        rag_result: RAG 分析结果字典
        action_item: 对应的行动建议字典（可为 None）
        batch_idx: 批次索引
        item_idx: 项目索引
    """
    review_id = rag_result.get("review_id", f"未知_{item_idx}")
    review_text = rag_result.get("review_text", "")
    conclusion = rag_result.get("conclusion", "❓ 需要人工判断")
    reason = rag_result.get("reason", "")
    evidence = rag_result.get("evidence", "")
    
    # 根据结论类型设置颜色、图标和视觉样式
    if "产品缺陷" in conclusion or "⚠️" in conclusion or "需进一步调查" in conclusion:
        # 情况 A：产品缺陷
        conclusion_type = "产品缺陷"
        card_style = "error"
        title_prefix = "🔴 [产品缺陷]"
        container_func = st.error
    elif "用户" in conclusion or "❓" in conclusion or "用户使用问题" in conclusion:
        # 情况 B：用户误解/操作不当
        conclusion_type = "用户误解"
        card_style = "warning"
        title_prefix = "⚠️ [用户误解]"
        container_func = st.warning
    elif "✅" in conclusion or "产品已知局限" in conclusion:
        # 情况 C：产品已知局限
        conclusion_type = "产品已知局限"
        card_style = "info"
        title_prefix = "ℹ️ [产品已知局限]"
        container_func = st.info
    else:
        # 其他情况
        conclusion_type = "其他问题"
        card_style = "info"
        title_prefix = "🔵 [其他问题]"
        container_func = st.info
    
    # 提取问题标题
    title_keywords = ["续航", "避障", "云台", "抖动", "电池", "图传", "GPS", "虚标", "硬件", "自检"]
    title = "未知问题"
    for keyword in title_keywords:
        if keyword in review_text:
            title = keyword + "相关问题"
            break
    
    # 生成唯一的 key
    unique_key = f"case_{batch_idx}_{item_idx}_{review_id}"
    
    # 创建完整的 Case 容器（使用 border=True 增强视觉分组）
    with st.container(border=True):
        # 1. Header: 风险标题 - 优化显示，避免重复图标
        st.markdown("")  # 添加顶部间距
        
        # 提取图标和文本（title_prefix 已经包含图标，不需要重复显示）
        # 例如：title_prefix = "🔴 [产品缺陷]" 或 "ℹ️ [产品已知局限]"
        st.markdown(f"### {title_prefix} {title}")
        st.caption(f"📋 评论ID: {review_id}")
        
        st.markdown("---")  # 添加分隔线，更清晰
        
        # 2. Section 1: 归因分析 (Evidence) - 优化布局
        st.markdown("#### 🔍 归因分析")
        st.markdown("")  # 添加小间距
        
        col_left, col_mid, col_right = st.columns([1, 1, 1])
        
        with col_left:
            st.markdown("**💬 用户原话**")
            st.markdown("")  # 小间距
            # 使用更友好的显示方式
            with st.container():
                container_func(review_text)
        
        with col_mid:
            st.markdown("**📖 RAG 证据**")
            st.markdown("")  # 小间距
            if evidence and evidence not in ["未在说明书中找到相关描述", "向量库未初始化，使用基础分析", ""]:
                if len(evidence) > 500:
                    with st.expander("📄 查看完整证据", expanded=False):
                        st.markdown(evidence)
                    with st.container():
                        container_func(evidence[:500] + "...")
                else:
                    with st.container():
                        container_func(evidence)
            elif evidence == "未在说明书中找到相关描述":
                st.warning("⚠️ 未在说明书中找到相关描述")
            else:
                st.warning("⚠️ 向量检索未启用或失败")
        
        with col_right:
            st.markdown("**🤖 AI 判定**")
            st.markdown("")  # 小间距
            with st.container():
                # 优化结论显示
                conclusion_text = conclusion.replace("**结论：**", "").strip()
                container_func(f"**结论：** {conclusion_text}")
                st.markdown("")  # 小间距
                # 优化分析显示
                analysis_text = reason if reason else '暂无详细分析'
                st.markdown(f"**分析：** {analysis_text}")
        
        # 3. Section 2: 决策落地 (Action) - 确保始终显示
        st.divider()  # 使用分割线清晰区分分析与行动
        st.markdown("##### 💡 决策落地")
        
        if action_item and action_item.get("title"):
            # 有 action 数据，正常显示
            action_type = action_item.get("action_type", "Jira Ticket")
            action_title = action_item.get("title", "")
            action_content = action_item.get("content", "")
            priority = action_item.get("priority", "Medium")
            
            # 优先级颜色
            priority_colors = {
                "High": "🔴",
                "Medium": "🟡",
                "Low": "🟢"
            }
            priority_icon = priority_colors.get(priority, "🟡")
            
            # 行动类型图标
            type_icons = {
                "Jira Ticket": "🐞",
                "Doc Update": "📝",
                "Email Draft": "📧",
                "Meeting": "📅"
            }
            type_icon = type_icons.get(action_type, "📋")
            
            # 显示行动建议信息
            st.markdown(f"**{type_icon} {action_title}** · {priority_icon} {priority} · {action_type}")
            
            # 显示内容
            if action_content:
                if len(action_content) > 500:
                    with st.expander("📄 查看完整内容", expanded=False):
                        st.markdown(action_content)
                    st.markdown(action_content[:500] + "...")
                else:
                    st.markdown(action_content)
            else:
                st.info("📝 行动建议内容生成中...")
            
            # Mock 按钮（根据类型使用不同样式）
            col_btn1, col_btn2 = st.columns([1, 1])
            with col_btn1:
                if action_type == "Jira Ticket":
                    if st.button("🚀 推送至 Jira", key=f"action_jira_{unique_key}", use_container_width=True, type="primary"):
                        import random
                        ticket_id = f"DJI-2025-{random.randint(1000, 9999)}"
                        st.toast(f"✅ 工单已创建！Ticket ID: {ticket_id}", icon="🎉")
                elif action_type == "Doc Update":
                    if st.button("📝 创建 Notion Task", key=f"action_notion_{unique_key}", use_container_width=True):
                        st.toast("✅ Notion 任务已创建！", icon="🎉")
                elif action_type == "Email Draft":
                    if st.button("📧 复制邮件", key=f"action_email_{unique_key}", use_container_width=True):
                        st.toast("✅ 邮件内容已复制到剪贴板！", icon="🎉")
                elif action_type == "Meeting":
                    if st.button("📅 创建会议", key=f"action_meeting_{unique_key}", use_container_width=True):
                        st.toast("✅ 会议已创建！", icon="🎉")
        else:
            # 没有 action 数据，显示友好的占位符
            st.warning("⚠️ **暂未生成对应的行动建议**")
            st.info("💡 系统正在分析中，行动建议将根据归因结果自动生成。")
            
            # 提供手动创建按钮
            with st.expander("🔧 手动创建行动建议", expanded=False):
                action_type_manual = st.selectbox(
                    "行动类型",
                    ["Jira Ticket", "Doc Update", "Email Draft", "Meeting"],
                    key=f"manual_action_type_{unique_key}"
                )
                action_title_manual = st.text_input(
                    "标题",
                    value=f"处理 {review_id} 的问题",
                    key=f"manual_action_title_{unique_key}"
                )
                action_content_manual = st.text_area(
                    "内容",
                    value=f"用户反馈：{review_text[:200]}...",
                    height=100,
                    key=f"manual_action_content_{unique_key}"
                )
                if st.button("✅ 创建行动建议", key=f"manual_action_create_{unique_key}"):
                    st.success("✅ 行动建议已创建（演示模式）")
                    st.toast("✅ 行动建议已创建！", icon="🎉")

