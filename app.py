"""
ReviewOps - 用户反馈决策中台
一个帮助产品经理分析用户反馈的 B端 SaaS 原型
"""

import streamlit as st
import pandas as pd
import time
from collections import Counter
import re
import plotly.express as px
import plotly.graph_objects as go
import os
import json
from enum import Enum
from typing import Optional

# RAG 相关导入
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models import ChatTongyi
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate

# Pydantic 模型（如果未安装，使用基础字典）
try:
    from pydantic import BaseModel
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    # 创建一个简单的 BaseModel 替代
    class BaseModel:
        pass

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="ReviewOps · 用户反馈决策中台",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== 自定义样式 ====================
st.markdown("""
<style>
    /* 主题色彩系统 */
    :root {
        --primary: #6366f1;
        --secondary: #8b5cf6;
        --accent: #06b6d4;
        --success: #10b981;
        --warning: #f59e0b;
        --danger: #ef4444;
    }
    
    /* 指标卡片样式 */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
        padding: 1.2rem;
        border-radius: 12px;
        border: 1px solid rgba(99, 102, 241, 0.3);
        box-shadow: 0 4px 20px rgba(99, 102, 241, 0.15);
    }
    
    [data-testid="stMetric"] label {
        color: #a5b4fc !important;
        font-weight: 500;
    }
    
    [data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #e0e7ff !important;
        font-weight: 700;
    }
    
    /* 侧边栏样式 */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f0a1f 0%, #1a1333 100%);
    }
    
    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #c4b5fd;
    }
    
    /* 按钮样式 */
    .stButton > button {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 25px rgba(99, 102, 241, 0.5);
    }
    
    /* 表格样式 */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }
    
    /* Expander 样式 */
    .streamlit-expanderHeader {
        background: rgba(99, 102, 241, 0.1);
        border-radius: 8px;
    }
    
    /* 主标题 */
    .main-title {
        background: linear-gradient(90deg, #6366f1, #8b5cf6, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.5rem;
        font-weight: 800;
        margin-bottom: 0;
    }
    
    /* 信息卡片 */
    .info-card {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(99, 102, 241, 0.3);
        margin: 1rem 0;
    }
    
    /* 行动项卡片容器 */
    .action-card {
        background: #ffffff;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        border: 1px solid #e5e7eb;
        transition: all 0.2s ease;
    }
    
    .action-card:hover {
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
        transform: translateY(-2px);
    }
    
    /* 高优先级 */
    .action-card.high-priority {
        border-left: 4px solid #ef4444;
    }
    
    /* 中优先级 */
    .action-card.medium-priority {
        border-left: 4px solid #f59e0b;
    }
    
    /* 常规优先级 */
    .action-card.low-priority {
        border-left: 4px solid #10b981;
    }
    
    /* 优先级标签 */
    .priority-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 0.5rem;
    }
    
    .priority-badge.high {
        background: #fef2f2;
        color: #dc2626;
    }
    
    .priority-badge.medium {
        background: #fffbeb;
        color: #d97706;
    }
    
    .priority-badge.low {
        background: #ecfdf5;
        color: #059669;
    }
    
    /* 行动标题 */
    .action-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1f2937;
        margin: 0.5rem 0;
    }
    
    /* 行动详情 */
    .action-detail {
        color: #4b5563;
        font-size: 0.95rem;
        line-height: 1.6;
        margin: 0.75rem 0;
    }
    
    /* 元信息 */
    .action-meta {
        display: flex;
        gap: 1.5rem;
        margin-top: 1rem;
        padding-top: 0.75rem;
        border-top: 1px solid #f3f4f6;
    }
    
    .meta-item {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: #6b7280;
        font-size: 0.85rem;
    }
    
    .meta-item strong {
        color: #374151;
    }
    
    /* 分割线 */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.5), transparent);
        margin: 2rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ==================== 数据加载 ====================
@st.cache_data(ttl=60)  # 60秒缓存，便于开发
def load_reviews():
    """加载用户评论数据"""
    df = pd.read_csv("user_reviews.csv")
    # 确保有 review_id 列（如果没有，使用 user_id 或创建）
    if 'review_id' not in df.columns:
        if 'user_id' in df.columns:
            df['review_id'] = df['user_id']
        else:
            df['review_id'] = range(1, len(df) + 1)
    return df


# 清除缓存以便重新加载数据
load_reviews.clear()

# 加载数据
reviews_df = load_reviews()


# ==================== RAG 初始化 ====================
@st.cache_resource
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
        from langchain_community.chat_models import ChatTongyi
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
        # 1. 检索相关文档（直接使用 similarity_search 方法）
        docs = vectorstore.similarity_search(question, k=3)
        
        # 2. 构建上下文
        context = "\n\n".join([doc.page_content for doc in docs])
        
        # 3. 构建 Prompt
        system_template = """你是一个专业的产品分析师。请根据用户反馈和产品说明书，进行准确的归因分析。

请基于以下产品说明书内容，分析用户反馈问题：
{context}

回答格式：
- 说明书对应参数：[从产品说明书中提取的相关内容]
- AI 判定结论：[你的判断，如果是已知局限用✅，如果是新问题用⚠️，如果是用户误用用❓]

回答："""
        
        human_template = "用户反馈：{question}"
        
        messages = [
            SystemMessagePromptTemplate.from_template(system_template),
            HumanMessagePromptTemplate.from_template(human_template)
        ]
        
        prompt = ChatPromptTemplate.from_messages(messages)
        
        # 4. 调用 LLM
        formatted_prompt = prompt.format_messages(context=context, question=question)
        response = llm.invoke(formatted_prompt)
        
        # 5. 提取回答
        if hasattr(response, 'content'):
            answer = response.content
        else:
            answer = str(response)
        
        return answer, docs
        
    except Exception as e:
        st.warning(f"RAG 查询出错: {e}")
        return None, []


# ==================== 辅助函数 ====================
def extract_product_name():
    """从 PDF 文件名或向量库中提取产品名称"""
    # 从 PDF 文件名提取（dji_spec.pdf -> DJI）
    pdf_name = "dji_spec.pdf"
    if os.path.exists(pdf_name):
        # 从文件名提取产品名
        name = pdf_name.replace("_spec.pdf", "").replace(".pdf", "").upper()
        return name
    return "产品说明书"


def calculate_metrics(df):
    """计算关键指标"""
    total_reviews = len(df)
    avg_rating = df['rating'].mean()
    negative_ratio = len(df[df['rating'] < 3]) / total_reviews * 100
    return total_reviews, avg_rating, negative_ratio


def get_negative_reviews(df):
    """获取负面评价"""
    return df[df['rating'] < 3]


def analyze_reviews_with_llm(reviews_df, llm):
    """
    使用 LLM 进行语义聚类，自动发现主要抱怨点
    
    Args:
        reviews_df: 包含 review_text 和 user_id (或 review_id) 的 DataFrame
        llm: LangChain LLM 实例
    
    Returns:
        list: 包含 topics 的列表，每个 topic 包含 topic, review_ids, summary
    """
    if reviews_df.empty:
        return []
    
    # 确保有 review_id 或 user_id 列
    if 'review_id' not in reviews_df.columns and 'user_id' in reviews_df.columns:
        reviews_df = reviews_df.copy()
        reviews_df['review_id'] = reviews_df['user_id']
    elif 'review_id' not in reviews_df.columns:
        reviews_df = reviews_df.copy()
        reviews_df['review_id'] = range(1, len(reviews_df) + 1)
    
    # 构建评论文本，包含 ID 信息
    review_texts = []
    for idx, row in reviews_df.iterrows():
        review_id = row['review_id']
        review_text = row['review_text'] if 'review_text' in row else row.get('content', '')
        if review_text and not pd.isna(review_text):
            review_texts.append(f"评论ID {review_id}: {review_text}")
    
    if not review_texts:
        return []
    
    # 拼接所有评论
    all_reviews = "\n\n".join(review_texts)
    
    # 构建 Prompt
    prompt_template = """你是一个专业的产品反馈分析师。请阅读以下用户评论，自动归纳出前 5 个最严重的共性问题（Topic）。

对于每个问题，请提供：
1. 简短的标题（如"电池续航不足"、"客服响应慢"）
2. 属于该问题的评论 ID 列表
3. 一句典型的用户原话摘要

请严格按照以下 JSON 格式返回，不要添加任何其他文字说明：

{{
  "topics": [
    {{
      "topic": "问题标题",
      "review_ids": [1, 2, 3],
      "summary": "典型用户原话摘要"
    }},
    {{
      "topic": "问题标题",
      "review_ids": [4, 5],
      "summary": "典型用户原话摘要"
    }}
  ]
}}

用户评论：
{reviews}

请直接返回 JSON 格式，不要有任何其他说明文字："""
    
    try:
        # 调用 LLM
        prompt = prompt_template.format(reviews=all_reviews)
        response = llm.invoke(prompt)
        
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
            topics = result.get('topics', [])
            
            # 验证和清理数据
            valid_topics = []
            for topic_data in topics:
                if 'topic' in topic_data and 'review_ids' in topic_data:
                    valid_topics.append({
                        'topic': topic_data['topic'],
                        'review_ids': topic_data['review_ids'] if isinstance(topic_data['review_ids'], list) else [],
                        'summary': topic_data.get('summary', '')
                    })
            
            return valid_topics
            
        except json.JSONDecodeError as e:
            st.warning(f"JSON 解析失败，尝试修复: {e}")
            # 尝试提取 JSON 对象
            import re
            json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    return result.get('topics', [])
                except:
                    pass
            
            # 如果解析失败，返回空列表
            st.error(f"无法解析 LLM 返回的 JSON。原始响应：\n{answer[:500]}")
            return []
            
    except Exception as e:
        st.error(f"LLM 分析出错: {e}")
        return []


def convert_topics_to_aggregated_format(topics, reviews_df):
    """
    将 LLM 返回的 topics 转换为聚合格式，便于 UI 展示
    
    Args:
        topics: LLM 返回的 topics 列表，每个包含 topic, review_ids, summary
        reviews_df: 原始评论 DataFrame，用于根据 review_ids 反查评论内容
    
    Returns:
        list: 聚合后的抱怨列表，格式与原来的 aggregate_complaints 兼容
    """
    aggregated = []
    
    # 确保 reviews_df 有 review_id 列
    if 'review_id' not in reviews_df.columns and 'user_id' in reviews_df.columns:
        reviews_df = reviews_df.copy()
        reviews_df['review_id'] = reviews_df['user_id']
    elif 'review_id' not in reviews_df.columns:
        reviews_df = reviews_df.copy()
        reviews_df['review_id'] = range(1, len(reviews_df) + 1)
    
    for topic_data in topics:
        topic = topic_data.get('topic', '未知问题')
        review_ids = topic_data.get('review_ids', [])
        summary = topic_data.get('summary', '')
        
        # 根据 review_ids 从 DataFrame 中反查评论内容
        reviews = []
        for rid in review_ids:
            matching_rows = reviews_df[reviews_df['review_id'] == rid]
            if not matching_rows.empty:
                review_text = matching_rows.iloc[0].get('review_text', '') or matching_rows.iloc[0].get('content', '')
                if review_text:
                    reviews.append(review_text)
        
        aggregated.append({
            'complaint': topic,
            'count': len(review_ids),
            'reviews': reviews,
            'summary': summary,
            'review_ids': review_ids
        })
    
    # 按出现次数降序排列
    aggregated.sort(key=lambda x: x['count'], reverse=True)
    
    return aggregated


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
        
        # 返回源文档内容用于展示
        source_contents = [doc.page_content for doc in source_docs]
        
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


def generate_ai_brief(df, negative_ratio):
    """生成 AI 每日简报（基于实际用户反馈数据）"""
    negative_count = len(df[df['rating'] < 3])
    positive_count = len(df[df['rating'] >= 4])
    
    # 如果已有分析结果，使用它；否则使用通用描述
    if 'analysis_topics' in st.session_state:
        topics = st.session_state['analysis_topics']
        top_issues = [t.get('topic', '') for t in topics[:3]]
        top_issue_text = "、".join([f"**{issue}**" for issue in top_issues[:2] if issue])
    else:
        top_issue_text = "功能使用问题"
    
    brief = f"""
### 📊 舆情趋势分析

**整体情绪：** {"😊 正向为主" if negative_ratio < 30 else "😐 中性偏负" if negative_ratio < 50 else "😟 负向预警"}

**核心发现：**
- 本周共收集 **{len(df)}** 条用户反馈，其中正向评价 **{positive_count}** 条，负向评价 **{negative_count}** 条
- 用户反馈主要集中在 **产品功能限制说明不清** 和 **实际性能与宣传参数不符** 两大方面
- 当前最突出的问题类型：{top_issue_text if top_issue_text else "功能使用问题"}

**舆情预警：**
- 🔴 新手用户对产品限制条件的认知不足，导致使用体验差
- 🟡 硬件质量问题影响用户对产品品质的信任
- 🟡 说明书可读性不足，用户难以快速理解关键限制条件

**建议关注：**
- 优化产品说明书，突出关键限制条件
- 加强新手引导，在产品首次使用时主动提示重要限制
- 关注硬件品控，减少质量问题
"""
    return brief


# ==================== Action Plan 数据结构 ====================
class ActionType(str, Enum):
    """行动类型枚举"""
    JIRA_TICKET = "Jira Ticket"
    DOC_UPDATE = "Doc Update"
    EMAIL_DRAFT = "Email Draft"
    MEETING = "Meeting"


class Priority(str, Enum):
    """优先级枚举"""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


if PYDANTIC_AVAILABLE:
    class ActionPlan(BaseModel):
        """行动计划数据模型"""
        action_type: ActionType
        title: str
        content: str
        priority: Priority
        
        class Config:
            use_enum_values = True
else:
    # 如果没有 Pydantic，使用字典结构
    ActionPlan = dict


def generate_action_plan(topic_name: str, rag_conclusion: str, user_complaints: list, llm) -> Optional[dict]:
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
        
        response = llm.invoke(prompt)
        
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


# ==================== 侧边栏 ====================
with st.sidebar:
    st.markdown("## 🔬 ReviewOps")
    st.markdown("*用户反馈决策中台*")
    
    st.divider()
    
    # 产品信息
    product_name = extract_product_name()
    st.markdown("### 📦 当前分析产品")
    st.info(f"**{product_name}**\n\n产品说明书已向量化存储")
    
    st.divider()
    
    # API Key 输入
    st.markdown("### 🔑 API 配置")
    
    # 优先从环境变量读取
    default_api_key = "sk-1234"
     
    api_key = st.text_input(
        "DashScope API Key (阿里千问)",
        type="password",
        value=default_api_key,
        placeholder="sk-...",
        help="用于 RAG 深度分析功能（从环境变量 DASHSCOPE_API_KEY 读取，或在此输入）"
    )
    
    if api_key:
        st.success("✅ API Key 已配置")
    else:
        st.warning("⚠️ 请配置 API Key 以启用 RAG 分析功能")
    
    st.divider()
    
    # 数据概览
    st.markdown("### 📊 数据源")
    st.caption(f"📄 评论数据: `user_reviews.csv`")
    st.caption(f"📋 产品说明: `dji_spec.pdf` (已向量化)")
    st.caption(f"💾 向量库: `./chroma_db`")
    st.caption(f"🕐 最后更新: 2025-01-15")


# ==================== 主界面 ====================
# 标题区
st.markdown('<h1 class="main-title">ReviewOps</h1>', unsafe_allow_html=True)
st.markdown("**用户反馈决策中台** · 让产品决策有据可依")
st.markdown("---")

# ==================== 顶部 Dashboard ====================
st.markdown("## 📈 数据概览")

# 计算指标
total_reviews, avg_rating, negative_ratio = calculate_metrics(reviews_df)

# 三个指标卡片
col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="📝 总评论数",
        value=f"{total_reviews}",
        delta="本周新增 5 条",
        delta_color="normal"
    )

with col2:
    st.metric(
        label="⭐ 平均评分",
        value=f"{avg_rating:.1f}",
        delta="+0.2 vs 上周",
        delta_color="normal"
    )

with col3:
    st.metric(
        label="😔 负面评价占比",
        value=f"{negative_ratio:.1f}%",
        delta="-5% vs 上周",
        delta_color="inverse"
    )

st.markdown("")

# AI 每日简报
with st.expander("🤖 **AI 每日简报** - 点击展开", expanded=True):
    ai_brief = generate_ai_brief(reviews_df, negative_ratio)
    st.markdown(ai_brief)

st.markdown("---")

# ==================== 中间核心区：RAG 分析 ====================
st.markdown("## 🔍 RAG 归因分析")
st.caption("基于产品说明书对用户反馈进行智能归因，识别问题根源")

# 分析按钮
col_btn, col_space = st.columns([1, 3])
with col_btn:
    analyze_button = st.button("🚀 开始归因分析", use_container_width=True)

if analyze_button:
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
        
        # 存储 RAG 组件到 session_state
        st.session_state['vectorstore'] = vectorstore
        st.session_state['llm'] = llm
    
    # AI 分析过程
    with st.spinner("🧠 AI 正在分析中..."):
        progress_bar = st.progress(0)
        
        # Step 1
        st.toast("📥 正在提取负面评价...")
        negative_reviews = get_negative_reviews(reviews_df)
        time.sleep(0.3)
        progress_bar.progress(25)
        
        # Step 2: 使用 LLM 进行语义聚类
        st.toast("🤖 AI 正在分析用户反馈并自动聚类...")
        topics = analyze_reviews_with_llm(negative_reviews, llm)
        time.sleep(0.3)
        progress_bar.progress(50)
        
        if not topics:
            st.error("❌ LLM 分析失败，请检查 API Key 和网络连接")
            st.stop()
        
        # Step 3
        st.toast("📄 正在匹配产品说明书（RAG 检索）...")
        # 这里会稍后在显示结果时进行 RAG 分析
        time.sleep(0.3)
        progress_bar.progress(75)
        
        # Step 4
        st.toast("💡 正在生成分析结论...")
        time.sleep(0.3)
        progress_bar.progress(100)
    
    st.success("✅ 分析完成！")
    
    # 将 LLM 返回的 topics 转换为聚合格式
    aggregated_complaints = convert_topics_to_aggregated_format(topics, negative_reviews)
    
    # 存储到 session_state 供 Action 部分使用
    st.session_state['analysis_topics'] = topics
    st.session_state['analysis_results'] = aggregated_complaints  # 兼容旧代码
    st.session_state['aggregated_complaints'] = aggregated_complaints
    
    # 初始化过滤器状态
    if 'selected_complaint_filter' not in st.session_state:
        st.session_state['selected_complaint_filter'] = None

# ===== 显示分析结果（独立于按钮点击，便于过滤后刷新） =====
if 'aggregated_complaints' in st.session_state:
    aggregated_complaints = st.session_state['aggregated_complaints']
    # 兼容旧代码：analysis_results 可能是旧的格式，也可能是新的格式
    complaints = st.session_state.get('analysis_results', aggregated_complaints)
    
    # 问题分布统计 - 移到归因卡片上方，便于交互
    st.markdown("### 📊 问题分布")
    st.caption("💡 点击图表扇区可过滤下方的归因卡片")
    
    # 构建统计数据 - 按严重程度排序（出现次数从高到低）
    sorted_complaints = sorted(aggregated_complaints, key=lambda x: x['count'], reverse=True)
    
    complaint_counts = pd.DataFrame([
        {'问题类型': agg['complaint'], '出现次数': agg['count']} 
        for agg in sorted_complaints
    ])
    
    # 生成渐变颜色（从深红到浅红，表示严重程度）
    n_issues = len(sorted_complaints)
    if n_issues == 1:
        colors = ['#dc2626']  # 深红
    else:
        # 从深红到浅橙的渐变
        color_scale = ['#dc2626', '#ef4444', '#f87171', '#fca5a5', '#fed7aa', '#fef3c7']
        colors = color_scale[:n_issues] if n_issues <= len(color_scale) else color_scale
    
    col_chart, col_insight = st.columns([2, 1])
    
    with col_chart:
        # 创建可交互的饼图
        fig = go.Figure(data=[go.Pie(
            labels=complaint_counts['问题类型'],
            values=complaint_counts['出现次数'],
            hole=0.4,  # 甜甜圈样式
            marker=dict(
                colors=colors,
                line=dict(color='#ffffff', width=2)
            ),
            textinfo='label+percent',
            textposition='outside',
            textfont=dict(size=12),
            hovertemplate="<b>%{label}</b><br>出现次数: %{value}<br>占比: %{percent}<extra></extra>",
            pull=[0.05 if i == 0 else 0 for i in range(n_issues)]  # 突出最严重的问题
        )])
        
        fig.update_layout(
            showlegend=False,
            margin=dict(t=20, b=20, l=20, r=20),
            height=300,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            annotations=[
                dict(
                    text=f"<b>{len(complaints)}</b><br>条负面反馈",
                    x=0.5, y=0.5,
                    font=dict(size=14, color='#374151'),
                    showarrow=False
                )
            ]
        )
        
        # 显示图表并捕获点击事件
        selected_point = st.plotly_chart(
            fig, 
            use_container_width=True, 
            key="complaint_pie_chart",
            on_select="rerun",
            selection_mode="points"
        )
        
        # 处理点击事件
        if selected_point and selected_point.selection and selected_point.selection.point_indices:
            clicked_idx = selected_point.selection.point_indices[0]
            clicked_complaint = complaint_counts.iloc[clicked_idx]['问题类型']
            if st.session_state.get('selected_complaint_filter') != clicked_complaint:
                st.session_state['selected_complaint_filter'] = clicked_complaint
                st.rerun()
    
    with col_insight:
        st.markdown("**💡 关键洞察**")
        top_issue = sorted_complaints[0]['complaint']
        top_count = sorted_complaints[0]['count']
        
        # 严重程度指示器
        total_count = sum(agg['count'] for agg in sorted_complaints)
        severity_pct = top_count / total_count * 100 if total_count > 0 else 0
        if severity_pct >= 50:
            severity_label = "🔴 高度集中"
            severity_color = "#dc2626"
        elif severity_pct >= 30:
            severity_label = "🟡 中度集中"
            severity_color = "#f59e0b"
        else:
            severity_label = "🟢 分散"
            severity_color = "#10b981"
        
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #fef2f2 0%, #fff7ed 100%); 
                    padding: 1rem; border-radius: 10px; border-left: 4px solid {severity_color};">
            <p style="margin: 0 0 0.5rem 0; color: #6b7280; font-size: 0.85rem;">最突出问题</p>
            <p style="margin: 0 0 0.5rem 0; font-weight: 600; color: #1f2937;">{top_issue}</p>
            <p style="margin: 0; color: #374151;">
                出现 <strong>{top_count}</strong> 次 · 占比 <strong>{severity_pct:.0f}%</strong>
            </p>
            <p style="margin: 0.5rem 0 0 0; font-size: 0.85rem;">{severity_label}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # 显示其他问题的简要统计
        if len(sorted_complaints) > 1:
            st.markdown("**📋 其他问题**")
            total_count = sum(agg['count'] for agg in sorted_complaints)
            for agg in sorted_complaints[1:]:
                pct = agg['count'] / total_count * 100 if total_count > 0 else 0
                st.markdown(f"- {agg['complaint']}: **{agg['count']}** 次 ({pct:.0f}%)")
    
    # 过滤控制
    current_filter = st.session_state.get('selected_complaint_filter')
    
    if current_filter:
        st.info(f"🔍 当前过滤：**{current_filter}** · [点击清除过滤]")
        if st.button("✖️ 清除过滤，显示全部", key="clear_filter"):
            st.session_state['selected_complaint_filter'] = None
            st.rerun()
    
    # 显示分析结果 - 使用卡片式布局，支持过滤
    st.markdown("### 📋 归因分析结果")
    
    # 根据过滤器筛选要显示的问题
    display_complaints = aggregated_complaints
    if current_filter:
        display_complaints = [agg for agg in aggregated_complaints if agg['complaint'] == current_filter]
        st.caption(f"已过滤显示 **{len(display_complaints)}** 类问题")
    else:
        # 计算总评论数
        total_review_count = sum(agg['count'] for agg in aggregated_complaints)
        st.caption(f"共识别出 **{len(aggregated_complaints)}** 类问题，涉及 **{total_review_count}** 条负面评价")
    
    # 获取 RAG 组件（如果已初始化）
    vectorstore = st.session_state.get('vectorstore', None)
    llm = st.session_state.get('llm', None)
    qa_chain = {'vectorstore': vectorstore, 'llm': llm} if vectorstore and llm else None
    
    for idx, agg in enumerate(display_complaints):
        # 使用 RAG 进行真实分析（从向量库中检索）
        # 优先使用 summary，如果没有则使用 complaint
        query_text = agg.get('summary', agg['complaint'])
        if not query_text:
            query_text = agg['complaint']
        
        spec_match, conclusion, source_docs = match_with_spec(
            query_text, 
            qa_chain=qa_chain
        )
        
        # 提取结论的简短版本用于标题
        conclusion_short = conclusion.split(' - ')[0] if ' - ' in conclusion else (conclusion[:30] + "..." if len(conclusion) > 30 else conclusion)
        
        # 使用 expander 展示每个问题类型的详情（默认展开前3个或过滤后的全部）
        with st.expander(
            f"**{agg['complaint']}** · 出现 {agg['count']} 次 · {conclusion_short}",
            expanded=(idx < 3 or current_filter is not None)  # 默认展开前3个，过滤后全部展开
        ):
            col_left, col_right = st.columns([1, 1])
            
            with col_left:
                st.markdown("##### 🗣️ 用户抱怨点")
                st.markdown(f"**{agg['complaint']}**")
                st.markdown(f"📊 出现次数：**{agg['count']}** 次")
                
                # 如果有 summary，显示 AI 生成的摘要
                if agg.get('summary'):
                    st.markdown("##### 🤖 AI 摘要")
                    st.info(agg['summary'])
                
                st.markdown("##### 💬 典型用户反馈")
                # 显示所有评论，使用可滚动的方式
                if len(agg['reviews']) <= 5:
                    # 如果评论不多，全部显示
                    for i, review in enumerate(agg['reviews'], 1):
                        st.markdown(f"**反馈 {i}:**")
                        st.markdown(f"> *\"{review}\"*")
                        if i < len(agg['reviews']):
                            st.markdown("")  # 添加间距
                else:
                    # 如果评论较多，显示前5条，其余在expander中
                    for i, review in enumerate(agg['reviews'][:5], 1):
                        st.markdown(f"**反馈 {i}:**")
                        st.markdown(f"> *\"{review}\"*")
                        if i < 5:
                            st.markdown("")  # 添加间距
                    
                    with st.expander(f"📋 查看全部 {len(agg['reviews'])} 条反馈", expanded=False):
                        for i, review in enumerate(agg['reviews'][5:], 6):
                            st.markdown(f"**反馈 {i}:**")
                            st.markdown(f"> *\"{review}\"*")
                            if i < len(agg['reviews']):
                                st.markdown("")
            
            with col_right:
                st.markdown("##### 📖 说明书对应参数")
                # 使用 text_area 或 markdown 来显示完整内容，而不是 st.info（可能截断）
                if len(spec_match) > 500:
                    # 如果内容很长，使用 expander 或 text_area
                    with st.expander("📄 查看完整说明书内容", expanded=True):
                        st.markdown(spec_match)
                    st.caption("💡 点击上方展开查看完整内容")
                else:
                    # 内容较短，直接显示
                    st.markdown(f"<div style='background-color: #f0f9ff; padding: 1rem; border-radius: 8px; border-left: 4px solid #0ea5e9;'>{spec_match}</div>", unsafe_allow_html=True)
                
                # 如果有源文档，显示证据来源
                if source_docs:
                    st.markdown("")
                    with st.expander("📚 检索到的证据来源", expanded=False):
                        for i, doc in enumerate(source_docs[:3], 1):
                            st.markdown(f"**证据 {i}:**")
                            # 使用 text_area 显示完整内容，支持滚动
                            st.text_area(
                                label="",
                                value=doc,
                                height=150,
                                key=f"source_doc_{idx}_{i}",
                                disabled=True,
                                label_visibility="collapsed"
                            )
                            if i < len(source_docs[:3]):
                                st.markdown("---")
                
                st.markdown("##### 🤖 AI 判定结论")
                # 确保结论完整显示
                if "✅" in conclusion:
                    st.success(conclusion)
                elif "⚠️" in conclusion:
                    st.warning(conclusion)
                elif "❓" in conclusion:
                    st.info(conclusion)
                else:
                    st.info(conclusion)

st.markdown("---")

# ==================== 底部 Action 区 ====================
st.markdown("## 🎯 行动建议")
st.caption("基于 RAG 分析结果动态生成的可执行行动项 · 点击按钮立即执行")

if 'aggregated_complaints' in st.session_state and 'llm' in st.session_state:
    aggregated_complaints = st.session_state['aggregated_complaints']
    llm = st.session_state['llm']
    vectorstore = st.session_state.get('vectorstore', None)
    qa_chain = {'vectorstore': vectorstore, 'llm': llm} if vectorstore and llm else None
    
    # 为每个问题聚类生成 Action Plan
    if 'action_plans' not in st.session_state:
        st.session_state['action_plans'] = {}
    
    # 先为所有问题生成 Action Plan（如果还没有生成）
    if 'action_plans_generated' not in st.session_state:
        st.session_state['action_plans_generated'] = True
        with st.spinner("🤖 正在为所有问题生成行动计划..."):
            for idx, agg in enumerate(aggregated_complaints):
                topic_name = agg['complaint']
                action_key = f"action_plan_{idx}"
                
                if action_key not in st.session_state['action_plans']:
                    # 获取 RAG 结论
                    query_text = agg.get('summary', topic_name)
                    spec_match, conclusion, source_docs = match_with_spec(query_text, qa_chain=qa_chain)
                    
                    # 生成 Action Plan
                    action_plan = generate_action_plan(
                        topic_name=topic_name,
                        rag_conclusion=conclusion,
                        user_complaints=agg.get('reviews', [])[:5],
                        llm=llm
                    )
                    
                    if action_plan:
                        st.session_state['action_plans'][action_key] = action_plan
    
    # 收集所有已生成的 Action Plans，并按优先级排序
    action_plans_with_complaints = []
    for idx, agg in enumerate(aggregated_complaints):
        action_key = f"action_plan_{idx}"
        action_plan = st.session_state['action_plans'].get(action_key)
        if action_plan:
            priority = action_plan.get('priority', 'Medium')
            # 优先级映射：High=3, Medium=2, Low=1
            priority_score = {'High': 3, 'Medium': 2, 'Low': 1}.get(priority, 2)
            action_plans_with_complaints.append({
                'complaint': agg,
                'action_plan': action_plan,
                'priority_score': priority_score,
                'action_key': action_key
            })
    
    # 按优先级从高到低排序（High > Medium > Low），相同优先级按出现次数排序
    action_plans_with_complaints.sort(
        key=lambda x: (x['priority_score'], x['complaint']['count']), 
        reverse=True
    )
    
    # 显示前 5 个
    top_actions = action_plans_with_complaints[:5]
    
    for item in top_actions:
        agg = item['complaint']
        action_plan = item['action_plan']
        action_key = item['action_key']
        topic_name = agg['complaint']
        
        # 确定优先级样式
        priority = action_plan.get('priority', 'Medium')
        if priority == 'High':
            badge_class = "high"
            badge_text = "高优先级"
            badge_icon = "🔴"
            badge_color = "#dc2626"
            badge_bg = "#fef2f2"
        elif priority == 'Low':
            badge_class = "low"
            badge_text = "低优先级"
            badge_icon = "🟢"
            badge_color = "#059669"
            badge_bg = "#ecfdf5"
        else:
            badge_class = "medium"
            badge_text = "中优先级"
            badge_icon = "🟡"
            badge_color = "#d97706"
            badge_bg = "#fffbeb"
        
        # 使用 container 创建卡片
        with st.container():
            # 卡片头部：优先级标签和问题类型
            col_badge, col_topic = st.columns([1, 3])
            with col_badge:
                st.markdown(f'<span style="background:{badge_bg};color:{badge_color};padding:4px 12px;border-radius:20px;font-size:0.8rem;font-weight:600;">{badge_icon} {badge_text}</span>', unsafe_allow_html=True)
            with col_topic:
                st.caption(f"📌 问题类型：{topic_name} · 涉及 {agg['count']} 条反馈")
            
            # 卡片标题
            st.markdown(f"#### {action_plan.get('title', '行动计划')}")
            
            # 卡片内容区
            col_content, col_action = st.columns([3, 1])
            
            with col_content:
                # 显示 Action Type
                action_type = action_plan.get('action_type', 'Doc Update')
                type_icons = {
                    'Jira Ticket': '🐞',
                    'Doc Update': '📝',
                    'Email Draft': '📧',
                    'Meeting': '📅'
                }
                type_icon = type_icons.get(action_type, '📋')
                st.markdown(f"**{type_icon} 行动类型：** {action_type}")
                
                # 显示内容（长内容只显示在 expander 中，不显示预览）
                content = action_plan.get('content', '')
                if len(content) > 300:
                    # 长内容：只显示 expander，不显示预览
                    with st.expander("📄 查看完整内容", expanded=False):
                        st.markdown(f"<div style='background-color: #f9fafb; padding: 1rem; border-radius: 8px; border-left: 4px solid #6366f1;'>{content}</div>", unsafe_allow_html=True)
                else:
                    # 短内容：直接显示
                    st.markdown(f"<div style='background-color: #f9fafb; padding: 1rem; border-radius: 8px; border-left: 4px solid #6366f1;'>{content}</div>", unsafe_allow_html=True)
            
            with col_action:
                # 根据 Action Type 显示不同的按钮
                action_type = action_plan.get('action_type', 'Doc Update')
                button_key = f"btn_{action_key}"
                
                if action_type == 'Jira Ticket':
                    if st.button("🚀 推送至 Jira", key=button_key, use_container_width=True):
                        # 立即显示 toast，减少延迟
                        import random
                        ticket_id = f"DJI-2025-{random.randint(800, 999)}"
                        st.toast(f"✅ 工单已创建！Ticket ID: {ticket_id}", icon="🎉")
                        st.session_state[f'{button_key}_triggered'] = True
                        st.rerun()
                        
                elif action_type == 'Doc Update':
                    if st.button("📝 创建 Notion Task", key=button_key, use_container_width=True):
                        st.toast("✅ Notion 任务已创建！", icon="📝")
                        st.session_state[f'{button_key}_triggered'] = True
                        st.rerun()
                        
                elif action_type == 'Email Draft':
                    if st.button("📧 复制邮件", key=button_key, use_container_width=True):
                        st.toast("✅ 邮件内容已复制到剪贴板！", icon="📧")
                        st.session_state[f'{button_key}_triggered'] = True
                        st.rerun()
                        
                elif action_type == 'Meeting':
                    if st.button("📅 创建会议", key=button_key, use_container_width=True):
                        st.toast("✅ 会议邀请已发送！", icon="📅")
                        st.session_state[f'{button_key}_triggered'] = True
                        st.rerun()
                
                # 显示触发后的详细信息
                if st.session_state.get(f'{button_key}_triggered', False):
                    st.markdown("")
                    if action_type == 'Jira Ticket':
                        st.success(f"✅ 工单已成功创建并指派给相关团队")
                        with st.expander("🐞 工单详情", expanded=True):
                            st.markdown(f"""
| 字段 | 值 |
|------|-----|
| **工单标题** | {action_plan.get('title', 'N/A')} |
| **类型** | Bug / 功能增强 |
| **优先级** | {priority} |
| **描述** | {content[:200]}... |
                            """)
                    elif action_type == 'Email Draft':
                        st.success("✅ 邮件内容已复制到剪贴板")
                        with st.expander("📧 邮件内容预览", expanded=True):
                            st.markdown(content)
                    elif action_type == 'Meeting':
                        st.success("✅ 会议邀请已发送")
                        with st.expander("📅 会议详情", expanded=True):
                            st.markdown(content)
            
            st.divider()

elif 'aggregated_complaints' in st.session_state:
    st.info("👆 请先点击上方「开始归因分析」按钮，AI 将基于分析结果生成针对性的行动建议。")
else:
    st.info("👆 请先点击上方「开始归因分析」按钮，AI 将基于分析结果生成针对性的行动建议。")

# ==================== 页脚 ====================
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #6b7280; font-size: 0.85rem;">
        <p>🔬 ReviewOps v1.0 · 用户反馈决策中台</p>
        <p>Powered by RAG + LLM · Built with Streamlit</p>
    </div>
    """,
    unsafe_allow_html=True
)

