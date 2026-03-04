"""
单条归因实验室 Tab
包含单条工单/用户反馈输入、归因分析（Tool 调用）、行动建议生成等逻辑。
"""

import streamlit as st
import random

# ==================== 已屏蔽的 ChromaDB/向量库逻辑（保留供后续恢复）====================
# from langchain_community.embeddings import DashScopeEmbeddings
# from langchain_community.vectorstores import Chroma
#
# def init_vectorstore(api_key):
#     """初始化向量数据库"""
#     if not api_key:
#         return None
#     try:
#         embeddings = DashScopeEmbeddings(
#             model="text-embedding-v3",
#             dashscope_api_key=api_key
#         )
#         vectorstore = Chroma(
#             persist_directory="./chroma_db",
#             embedding_function=embeddings
#         )
#         return vectorstore
#     except Exception as e:
#         st.error(f"向量库初始化失败: {e}")
#         return None
# ==================== 以上为注释掉的 RAG 逻辑 ====================


from langchain_community.chat_models import ChatTongyi


@st.cache_resource
def init_llm(api_key):
    """初始化 LLM"""
    if not api_key:
        return None

    try:
        llm = ChatTongyi(
            model="qwen-plus",
            temperature=0,
            dashscope_api_key=api_key
        )
        return llm
    except Exception as e:
        st.error(f"LLM 初始化失败: {e}")
        return None


# ==================== 已屏蔽的 Chroma RAG 查询逻辑（保留供后续恢复）====================
# def perform_rag_query(vectorstore, llm, question):
#     """执行 RAG 查询：检索 + 生成"""
#     ... (Chroma similarity_search + LLM 生成)
# ==================== 以上为注释掉的 RAG 逻辑 ====================


def match_with_spec(complaint, qa_chain=None):
    """将用户客诉与知识库匹配：使用 Tool 调用（发版记录/已知缺陷/API SOP）进行归因分析。"""
    # 无 LLM 时的后备：B2B 场景简单关键词匹配
    if not qa_chain or not qa_chain.get("llm"):
        if "401" in complaint or "403" in complaint or "HMAC" in complaint or "API Token" in complaint or "Webhook" in complaint or "授权" in complaint:
            spec_match = "SOP 排查手册：遇到 HMAC validation failed 或 401 错误，通常是商家在 Shopify 后台重置了 API Token 但未在我们的系统更新。请引导商家重新授权。"
            conclusion = "✅ 产品已知局限 / 配置问题 - 建议按 SOP 引导重新授权"
        elif "昨天还好" in complaint or "今天突然" in complaint or "更新之后" in complaint or "发版" in complaint:
            spec_match = "发版记录 2026-03-02：重构了 USPS 物流轨迹抓取爬虫模块，增加了一层限流校验。"
            conclusion = "⚠️ 需进一步调查 - 可能与近期发版相关"
        elif "又来了" in complaint or "一直这样" in complaint or "老毛病" in complaint:
            spec_match = "已知缺陷 JIRA-1042：带有阿拉伯语地址的 Shopify 订单同步时，特定字符会导致解析超时。目前仍在排期修复中。"
            conclusion = "✅ 产品已知局限 - 已知缺陷库中有相关记录"
        else:
            spec_match = "未在知识库中找到对应描述，建议使用 Tool 分析。"
            conclusion = "⚠️ 需进一步调查 - 可能是新发现的问题"
        return spec_match, conclusion, []

    # 使用 Tool 调用进行归因分析（L2 技术支持智能体）
    try:
        from src.nodes.rag import run_attribution_with_tools
        conclusion, reason, evidence, tool_outputs = run_attribution_with_tools(qa_chain["llm"], complaint)
        if conclusion is None:
            conclusion = "❓ 需要人工判断"
        spec_match = evidence if evidence else "\n\n".join(tool_outputs) if tool_outputs else "未获取到工具返回证据"
        if not spec_match:
            spec_match = "未在知识库中找到对应描述"
        # 用于展示的“证据来源”列表（此处为工具返回的文本）
        source_contents = list(tool_outputs) if tool_outputs else []
        return spec_match, conclusion, source_contents
    except Exception as e:
        st.warning(f"归因分析出错: {e}，使用后备方案")
        spec_match = "未在知识库中找到对应描述"
        conclusion = "⚠️ 需进一步调查 - 可能是新发现的问题"
        return spec_match, conclusion, []


def generate_action_plan(topic_name: str, rag_conclusion: str, user_complaints: list, llm):
    """
    使用 LLM 根据 RAG 分析结果动态生成行动计划
    
    Args:
        topic_name: 问题聚类名称
        rag_conclusion: RAG 分析出的归因结论
        user_complaints: 典型用户原话列表
        llm: LangChain LLM 实例
    
    Returns:
        dict: ActionPlan 对象（包含 action_type, title, content, priority）
    """
    if not llm:
        return None
    
    import json
    import re
    from langchain_core.messages import HumanMessage
    
    # 构建用户抱怨摘要
    complaints_text = "\n".join([f"- {complaint}" for complaint in user_complaints[:5]])
    
    # 构建 Prompt
    prompt_template = """你是 B2B 电商与物流 SaaS 的 L2 技术支持智能体，能够根据问题性质做出决策。

请根据以下信息，生成一个具体的行动计划：

**问题类型：** {topic_name}

**RAG 归因结论：** {rag_conclusion}

**典型用户反馈：**
{complaints}

**决策规则：**
- 如果归因是 **产品缺陷/Bug** -> 生成 Jira Ticket，包含标题、描述、复现步骤、优先级
- 如果归因是 **用户误操作/文档不清** -> 生成 Doc Update（更新文档/SOP）或 Email Draft（客服话术）
- 如果归因是 **物流/服务问题** -> 生成 Email Draft（给物流商或客服主管）
- 如果归因是 **复杂问题需要讨论** -> 生成 Meeting（会议安排）

请严格按照以下 JSON 格式返回，不要添加任何其他文字说明：

{{
  "action_type": "Jira Ticket" | "Doc Update" | "Email Draft" | "Meeting",
  "title": "行动的简短标题（如：创建 P0 级 Jira 工单：修复 API 401 授权问题）",
  "content": "行动的详细内容（如工单的 Description 或邮件的正文，要具体可执行）",
  "priority": "High" | "Medium" | "Low"
}}

请直接返回 JSON 格式，不要有任何其他说明文字："""
    
    try:
        prompt = prompt_template.format(
            topic_name=topic_name,
            rag_conclusion=rag_conclusion,
            complaints=complaints_text
        )
        
        response = llm.invoke([HumanMessage(content=prompt)])
        
        # 提取回答
        if hasattr(response, 'content'):
            answer = response.content
        else:
            answer = str(response)
        
        # 尝试提取 JSON（可能包含 markdown 代码块）
        json_str = answer.strip()
        
        # 移除可能的 markdown 代码块标记
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        elif json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        json_str = json_str.strip()
        
        # 解析 JSON
        try:
            result = json.loads(json_str)
            
            # 验证必需字段
            required_fields = ['action_type', 'title', 'content', 'priority']
            if all(field in result for field in required_fields):
                # 验证 action_type
                valid_types = ['Jira Ticket', 'Doc Update', 'Email Draft', 'Meeting']
                if result['action_type'] not in valid_types:
                    result['action_type'] = 'Doc Update'  # 默认值
                
                # 验证 priority
                valid_priorities = ['High', 'Medium', 'Low']
                if result['priority'] not in valid_priorities:
                    result['priority'] = 'Medium'  # 默认值
                
                return result
            else:
                st.warning(f"LLM 返回的 JSON 缺少必需字段。原始响应：\n{answer[:500]}")
                return None
                
        except json.JSONDecodeError as e:
            st.warning(f"JSON 解析失败，尝试修复: {e}")
            # 尝试提取 JSON 对象
            json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    return result
                except:
                    pass
            
            st.error(f"无法解析 LLM 返回的 JSON。原始响应：\n{answer[:500]}")
            return None
            
    except Exception as e:
        st.error(f"生成行动计划时出错: {e}")
        return None


def render_tab(api_key):
    """
    渲染单条归因实验室 Tab
    
    Args:
        api_key: DashScope API Key
    """
    st.markdown("### 🔬 单条工单归因分析")
    st.caption("输入单条用户反馈/工单内容，由 L2 技术支持智能体调用工具（发版记录/已知缺陷/API SOP）进行归因分析")

    user_input = st.text_area(
        "📝 请输入工单内容或用户反馈",
        placeholder="例如：昨天还好好的，今天早上 USPS 的轨迹全不更新了！",
        height=100,
        key="manual_review_input"
    )
    
    analyze_button = st.button("🚀 开始归因分析", use_container_width=True, key="analyze_btn_manual")
    
    if analyze_button:
        # 检查输入
        if not user_input or not user_input.strip():
            st.warning("⚠️ 请输入工单内容或用户反馈")
            st.stop()
        
        # 检查 API Key
        if not api_key:
            st.error("❌ 请先在侧边栏配置 DashScope API Key")
            st.stop()
        
        # 初始化 LLM（已改用 Tool 调用，不再依赖向量库）
        with st.spinner("🔧 正在初始化智能体..."):
            llm = init_llm(api_key)
            if not llm:
                st.error("❌ 初始化失败，请检查 API Key")
                st.stop()

        # 执行归因分析（Tool 调用：发版记录 / 已知缺陷 / API SOP）
        with st.spinner("🧠 AI 正在分析中（工具调用）..."):
            spec_match, conclusion, source_docs = match_with_spec(
                user_input,
                qa_chain={"llm": llm}
            )
        
        st.success("✅ 分析完成！")
        
        # 显示分析结果
        st.markdown("---")
        st.markdown("### 📊 分析结果")
        
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("##### 💬 用户反馈")
            st.info(user_input)
            
            st.markdown("##### 🤖 AI 判定结论")
            if "✅" in conclusion:
                st.success(conclusion)
            elif "⚠️" in conclusion:
                st.warning(conclusion)
            elif "❓" in conclusion:
                st.info(conclusion)
            else:
                st.info(conclusion)
        
        with col_right:
            st.markdown("##### 📖 工具/知识库证据")
            if len(spec_match) > 500:
                with st.expander("📄 查看完整证据内容", expanded=True):
                    st.markdown(spec_match)
            else:
                st.markdown(f"<div style='background-color: #f0f9ff; padding: 1rem; border-radius: 8px; border-left: 4px solid #0ea5e9;'>{spec_match}</div>", unsafe_allow_html=True)
            
            # 显示证据来源
            if source_docs:
                st.markdown("")
                with st.expander(f"📚 检索到的证据来源 ({len(source_docs)} 条)", expanded=False):
                    for i, doc in enumerate(source_docs, 1):
                        st.markdown(f"**证据 {i}:**")
                        st.text_area(
                            label="",
                            value=doc,
                            height=150,
                            key=f"manual_source_doc_{i}",
                            disabled=True,
                            label_visibility="collapsed"
                        )
                        if i < len(source_docs):
                            st.markdown("---")
        
        st.markdown("---")
        st.markdown("### 💡 行动建议")

        action_plan = generate_action_plan(
            topic_name="单条工单分析",
            rag_conclusion=conclusion,
            user_complaints=[user_input],
            llm=llm
        )
        
        if action_plan:
            action_type = action_plan.get('action_type', 'Doc Update')
            title = action_plan.get('title', '')
            content = action_plan.get('content', '')
            priority = action_plan.get('priority', 'Medium')
            
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
            
            with st.expander(f"{type_icon} **{title}** · {priority_icon} {priority} · {action_type}", expanded=True):
                st.markdown(f"**优先级：** {priority}")
                st.markdown(f"**类型：** {action_type}")
                st.markdown(f"**内容：**")
                if len(content) > 500:
                    st.text_area("", value=content, height=150, disabled=True, key="manual_action_content", label_visibility="collapsed")
                else:
                    st.markdown(content)
                
                # Mock 按钮
                if action_type == "Jira Ticket":
                    if st.button("🚀 推送至 Jira", key="manual_jira", use_container_width=True):
                        ticket_id = f"RO-2025-{random.randint(800, 999)}"
                        st.toast(f"✅ 工单已创建！Ticket ID: {ticket_id}", icon="🎉")
                elif action_type == "Doc Update":
                    if st.button("📝 创建 Notion Task", key="manual_notion", use_container_width=True):
                        st.toast("✅ Notion 任务已创建！", icon="🎉")
                elif action_type == "Email Draft":
                    if st.button("📧 复制邮件", key="manual_email", use_container_width=True):
                        st.toast("✅ 邮件内容已复制到剪贴板！", icon="🎉")
                elif action_type == "Meeting":
                    if st.button("📅 创建会议", key="manual_meeting", use_container_width=True):
                        st.toast("✅ 会议已创建！", icon="🎉")
    else:
        st.info("👆 请输入工单内容并点击「开始归因分析」按钮")

