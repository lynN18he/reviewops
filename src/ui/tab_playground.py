"""
单条归因实验室 Tab
包含单条评论输入、RAG 分析、行动建议生成等所有逻辑
"""

import streamlit as st
import random
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models import ChatTongyi
from langchain_community.vectorstores import Chroma


def init_vectorstore(api_key):
    """初始化向量数据库"""
    if not api_key:
        return None
    
    try:
        embeddings = DashScopeEmbeddings(
            model="text-embedding-v3",  # 与 injest.py 保持一致，使用 v3 模型（1536 维）
            dashscope_api_key=api_key
        )
        
        vectorstore = Chroma(
            persist_directory="./chroma_db",
            embedding_function=embeddings
        )
        return vectorstore
    except Exception as e:
        st.error(f"向量库初始化失败: {e}")
        return None


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


def perform_rag_query(vectorstore, llm, question):
    """执行 RAG 查询：检索 + 生成"""
    if not vectorstore or not llm:
        return None, []
    
    try:
        # 1. 检索相关文档（使用 similarity_search_with_score 获取距离分数）
        # 使用更大的 k 值，然后去重和过滤
        try:
            docs_with_scores = vectorstore.similarity_search_with_score(question, k=10)
        except:
            # 如果不支持 similarity_search_with_score，回退到普通搜索
            docs = vectorstore.similarity_search(question, k=5)
            # 简单去重，返回所有不重复的文档
            unique_docs = []
            seen_contents = set()
            for doc in docs:
                content_fingerprint = doc.page_content[:150].strip()
                if content_fingerprint not in seen_contents:
                    seen_contents.add(content_fingerprint)
                    unique_docs.append(doc)
            docs = unique_docs  # 返回所有去重后的文档，不限制数量
        else:
            # 2. 去重：基于文档内容的相似度去重
            # ChromaDB 返回的是距离（distance），越小越相似
            # 通常距离 < 1.5 表示比较相关
            unique_docs = []
            seen_contents = set()
            max_distance = 1.5  # 最大距离阈值（根据实际调整）
            
            for doc, distance in docs_with_scores:
                # 过滤距离过大的结果（相似度太低）
                if distance > max_distance:
                    continue
                
                # 检查内容是否重复（使用前150个字符作为指纹，更准确）
                content_fingerprint = doc.page_content[:150].strip()
                if content_fingerprint not in seen_contents:
                    seen_contents.add(content_fingerprint)
                    unique_docs.append(doc)
                    # 不再限制数量，返回所有相关且不重复的文档
            
            docs = unique_docs  # 返回所有相关且去重后的文档
        
        # 3. 构建上下文
        context = "\n\n".join([doc.page_content for doc in docs])
        
        # 3. 构建 Prompt
        from langchain_core.messages import HumanMessage, SystemMessage
        
        system_template = """你是一个专业的产品分析师。请根据用户反馈和产品说明书，进行准确的归因分析。

请基于以下产品说明书内容，分析用户反馈问题：
{context}

回答格式：
- 说明书对应参数：[从产品说明书中提取的相关内容]
- AI 判定结论：[你的判断，如果是已知局限用✅，如果是新问题用⚠️，如果是用户误用用❓]

回答："""
        
        human_template = "用户反馈：{question}"
        
        system_prompt = SystemMessage(content=system_template.format(context=context))
        human_prompt = HumanMessage(content=human_template.format(question=question))
        
        # 4. 调用 LLM
        response = llm.invoke([system_prompt, human_prompt])
        
        # 5. 提取回答
        if hasattr(response, 'content'):
            answer = response.content
        else:
            answer = str(response)
        
        return answer, docs
        
    except Exception as e:
        st.error(f"RAG 查询失败: {e}")
        return None, []


def match_with_spec(complaint, qa_chain=None):
    """将用户抱怨与产品说明书进行匹配（使用 RAG）"""
    
    # 如果没有 RAG 链，使用简单的关键词匹配作为后备
    if not qa_chain:
        if '中文播客' in complaint or '中文' in complaint:
            spec_match = "音频与语言限制：Audio Overview 目前强调为实验性功能...中文播客式输出体验明显弱于英文"
            conclusion = "✅ 产品已知局限 - 说明书已明确标注中文支持有限"
        elif 'PDF' in complaint or '图表' in complaint:
            spec_match = "内容与文件限制：对纯图片 PDF、复杂表格或图像信息支持有限，图表和图像型 PDF 在解析和检索时仍可能丢失或弱化"
            conclusion = "✅ 产品已知局限 - 说明书已明确标注图表解析受限"
        else:
            spec_match = "未在说明书中找到对应描述"
            conclusion = "⚠️ 需进一步调查 - 可能是新发现的问题"
        return spec_match, conclusion, []
    
    # 使用 RAG 进行真实检索和分析
    try:
        query = f"用户反馈：{complaint}。请分析这是产品已知局限还是新问题。"
        answer, source_docs = perform_rag_query(qa_chain['vectorstore'], qa_chain['llm'], query)
        
        if not answer:
            raise Exception("RAG 查询返回空结果")
        
        # 解析回答，提取说明书参数和结论
        spec_match = ""
        conclusion = ""
        
        # 从回答中提取信息
        if "说明书对应参数" in answer:
            parts = answer.split("说明书对应参数：")
            if len(parts) > 1:
                spec_part = parts[1].split("AI 判定结论：")[0].strip()
                spec_match = spec_part if spec_part else "未找到相关说明"
        else:
            spec_match = "未在说明书中找到对应描述"
        
        if "AI 判定结论" in answer:
            conclusion = answer.split("AI 判定结论：")[-1].strip()
        else:
            # 从回答中推断结论
            if "已知局限" in answer or "✅" in answer:
                conclusion = "✅ 产品已知局限 - " + answer[:50]
            elif "新问题" in answer or "⚠️" in answer:
                conclusion = "⚠️ 需进一步调查 - " + answer[:50]
            else:
                conclusion = "❓ 需要人工判断 - " + answer[:50]
        
        # 如果没有提取到，使用源文档内容
        if not spec_match and source_docs:
            spec_match = "\n\n".join([doc.page_content[:200] + "..." for doc in source_docs[:2]])
        
        # 返回源文档内容用于展示（去重）
        source_contents = []
        seen_contents = set()
        for doc in source_docs:
            content = doc.page_content
            # 使用前100个字符作为指纹去重
            fingerprint = content[:100].strip()
            if fingerprint not in seen_contents:
                seen_contents.add(fingerprint)
                source_contents.append(content)
        
        return spec_match, conclusion, source_contents
        
    except Exception as e:
        st.warning(f"RAG 分析出错: {e}，使用后备方案")
        # 后备方案
        if '中文播客' in complaint or '中文' in complaint:
            spec_match = "音频与语言限制：Audio Overview 目前强调为实验性功能...中文播客式输出体验明显弱于英文"
            conclusion = "✅ 产品已知局限 - 说明书已明确标注中文支持有限"
        elif 'PDF' in complaint or '图表' in complaint:
            spec_match = "内容与文件限制：对纯图片 PDF、复杂表格或图像信息支持有限，图表和图像型 PDF 在解析和检索时仍可能丢失或弱化"
            conclusion = "✅ 产品已知局限 - 说明书已明确标注图表解析受限"
        else:
            spec_match = "未在说明书中找到对应描述"
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
    prompt_template = """你是一个能够根据问题性质做出决策的产品经理。

请根据以下信息，生成一个具体的行动计划：

**问题类型：** {topic_name}

**RAG 归因结论：** {rag_conclusion}

**典型用户反馈：**
{complaints}

**决策规则：**
- 如果归因是 **产品缺陷/Bug** -> 生成 Jira Ticket，包含标题、描述、复现步骤、优先级
- 如果归因是 **用户误操作/文档不清** -> 生成 Doc Update（更新说明书）或 Email Draft（客服话术）
- 如果归因是 **物流/服务问题** -> 生成 Email Draft（给物流商或客服主管）
- 如果归因是 **复杂问题需要讨论** -> 生成 Meeting（会议安排）

请严格按照以下 JSON 格式返回，不要添加任何其他文字说明：

{{
  "action_type": "Jira Ticket" | "Doc Update" | "Email Draft" | "Meeting",
  "title": "行动的简短标题（如：创建 P0 级 Jira 工单：修复云台抖动）",
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
    st.markdown("### 🔬 单条评论归因分析")
    st.caption("输入单条用户评论，进行深度 RAG 归因分析")
    
    # 单条评论输入
    user_input = st.text_area(
        "📝 请输入用户评论",
        placeholder="例如：夜间飞行时避障功能完全失效，差点撞墙...",
        height=100,
        key="manual_review_input"
    )
    
    analyze_button = st.button("🚀 开始归因分析", use_container_width=True, key="analyze_btn_manual")
    
    if analyze_button:
        # 检查输入
        if not user_input or not user_input.strip():
            st.warning("⚠️ 请输入用户评论")
            st.stop()
        
        # 检查 API Key
        if not api_key:
            st.error("❌ 请先在侧边栏配置 DashScope API Key")
            st.stop()
        
        # 初始化 RAG 组件
        with st.spinner("🔧 正在初始化 RAG 系统..."):
            vectorstore = init_vectorstore(api_key)
            llm = init_llm(api_key)
            
            if not vectorstore or not llm:
                st.error("❌ RAG 系统初始化失败，请检查 API Key 和向量库")
                st.stop()
        
        # 执行 RAG 分析
        with st.spinner("🧠 AI 正在分析中..."):
            spec_match, conclusion, source_docs = match_with_spec(
                user_input,
                qa_chain={'vectorstore': vectorstore, 'llm': llm}
            )
        
        st.success("✅ 分析完成！")
        
        # 显示分析结果
        st.markdown("---")
        st.markdown("### 📊 分析结果")
        
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("##### 💬 用户评论")
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
            st.markdown("##### 📖 说明书对应参数")
            if len(spec_match) > 500:
                with st.expander("📄 查看完整说明书内容", expanded=True):
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
        
        # 生成单条评论的 Action Plan
        st.markdown("---")
        st.markdown("### 💡 行动建议")
        
        action_plan = generate_action_plan(
            topic_name="单条评论分析",
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
                        ticket_id = f"DJI-2025-{random.randint(800, 999)}"
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
        st.info("👆 请输入用户评论并点击「开始归因分析」按钮")

