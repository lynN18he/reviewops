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
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# RAG 相关导入
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.chat_models import ChatTongyi
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate

# Pydantic 模型（如果未安装，使用基础字典）
try:
    from pydantic import BaseModel, ConfigDict
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    # 创建一个简单的 BaseModel 替代
    class BaseModel:
        pass
    ConfigDict = None

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
    
    /* 侧边栏样式 - 优化颜色使其更明显和用户友好 */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #334155 100%) !important;
        border-right: 2px solid rgba(99, 102, 241, 0.3);
    }
    
    [data-testid="stSidebar"] .stMarkdown h1,
    [data-testid="stSidebar"] .stMarkdown h2,
    [data-testid="stSidebar"] .stMarkdown h3 {
        color: #e0e7ff !important;
        font-weight: 600;
    }
    
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] .stMarkdown {
        color: #cbd5e1 !important;
    }
    
    [data-testid="stSidebar"] .stInfo {
        background-color: rgba(99, 102, 241, 0.15) !important;
        border-left: 3px solid #6366f1 !important;
        color: #e0e7ff !important;
    }
    
    [data-testid="stSidebar"] .stSuccess {
        background-color: rgba(16, 185, 129, 0.15) !important;
        border-left: 3px solid #10b981 !important;
        color: #d1fae5 !important;
    }
    
    [data-testid="stSidebar"] .stWarning {
        background-color: rgba(245, 158, 11, 0.15) !important;
        border-left: 3px solid #f59e0b !important;
        color: #fef3c7 !important;
    }
    
    [data-testid="stSidebar"] .stCaption {
        color: #94a3b8 !important;
    }
    
    [data-testid="stSidebar"] .stDivider {
        border-color: rgba(99, 102, 241, 0.2) !important;
    }
    
    [data-testid="stSidebar"] input[type="text"],
    [data-testid="stSidebar"] input[type="password"] {
        background-color: rgba(30, 41, 59, 0.5) !important;
        border: 1px solid rgba(99, 102, 241, 0.3) !important;
        color: #e0e7ff !important;
    }
    
    [data-testid="stSidebar"] input[type="text"]:focus,
    [data-testid="stSidebar"] input[type="password"]:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2) !important;
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
    
    /* Toast 通知位置调整 - 让弹框更靠近按钮 */
    [data-testid="stToast"] {
        position: fixed !important;
        top: 20px !important;
        right: 20px !important;
        z-index: 999999 !important;
        min-width: 300px !important;
        max-width: 400px !important;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3) !important;
        border-radius: 12px !important;
        animation: slideInRight 0.3s ease-out !important;
    }
    
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    /* 确保 toast 内容可见 */
    [data-testid="stToast"] > div {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%) !important;
        color: #e0e7ff !important;
        padding: 1rem 1.25rem !important;
        border: 1px solid rgba(99, 102, 241, 0.3) !important;
    }
    
    [data-testid="stToast"] [data-baseweb="notification"] {
        background: transparent !important;
        color: #e0e7ff !important;
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
    """计算关键指标 - 确保所有评论（包括正面和负面）都被正确统计"""
    # 处理空 DataFrame
    if df.empty or len(df) == 0:
        return 0, 0.0, 0.0
    
    total_reviews = len(df)
    
    # 计算平均评分，处理 NaN 值
    # 重要：必须计算所有评论的平均分，包括正面、负面和中性评论
    if 'rating' not in df.columns:
        avg_rating = 0.0
    else:
        # 确保 rating 是数值类型
        rating_series = pd.to_numeric(df['rating'], errors='coerce')
        # 过滤掉 NaN 值后计算平均值（包括所有有效评分）
        valid_ratings = rating_series.dropna()
        if len(valid_ratings) > 0:
            # 计算所有有效评分的平均值（包括 1-5 星的所有评分）
            avg_rating = float(valid_ratings.mean())
        else:
            avg_rating = 0.0
    
    # 计算负面评价占比，处理除零情况
    # 重要：负面评价占比 = 负面评论数 / 总评论数 * 100
    # 总评论数包括所有评论（正面、负面、中性）
    if total_reviews == 0:
        negative_ratio = 0.0
    else:
        if 'rating' in df.columns:
            # 确保 rating 是数值类型后再比较
            rating_series = pd.to_numeric(df['rating'], errors='coerce')
            # 负面评价：rating < 3（1星和2星）
            # 注意：这里只计算负面评论数，分母是总评论数（包括正面评论）
            negative_count = len(rating_series[rating_series < 3].dropna())
        else:
            negative_count = 0
        # 负面占比 = 负面评论数 / 总评论数 * 100
        negative_ratio = (negative_count / total_reviews) * 100
    
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
    
    # 收集所有已归类的 review_ids，用于检测重复和遗漏
    all_classified_review_ids = set()
    
    for topic_data in topics:
        topic = topic_data.get('topic', '未知问题')
        review_ids = topic_data.get('review_ids', [])
        summary = topic_data.get('summary', '')
        
        # 去重：如果同一个 review_id 出现在多个 topics 中，只保留第一次出现的
        unique_review_ids = []
        for rid in review_ids:
            if rid not in all_classified_review_ids:
                unique_review_ids.append(rid)
                all_classified_review_ids.add(rid)
        
        # 如果去重后没有有效的 review_ids，跳过这个 topic
        if not unique_review_ids:
            continue
        
        # 根据 review_ids 从 DataFrame 中反查评论内容
        reviews = []
        for rid in unique_review_ids:
            matching_rows = reviews_df[reviews_df['review_id'] == rid]
            if not matching_rows.empty:
                review_text = matching_rows.iloc[0].get('review_text', '') or matching_rows.iloc[0].get('content', '')
                if review_text:
                    reviews.append(review_text)
        
        aggregated.append({
            'complaint': topic,
            'count': len(unique_review_ids),  # 使用去重后的数量
            'reviews': reviews,
            'summary': summary,
            'review_ids': unique_review_ids  # 保存去重后的 review_ids
        })
    
    # 按出现次数降序排列
    aggregated.sort(key=lambda x: x['count'], reverse=True)
    
    # 验证：检查是否有遗漏的负面评论
    all_negative_review_ids = set(reviews_df['review_id'].tolist())
    unclassified_ids = all_negative_review_ids - all_classified_review_ids
    
    if unclassified_ids:
        # 如果有未归类的评论，创建一个"其他问题"类别，确保所有评论都被统计
        unclassified_reviews = []
        for rid in unclassified_ids:
            matching_rows = reviews_df[reviews_df['review_id'] == rid]
            if not matching_rows.empty:
                review_text = matching_rows.iloc[0].get('review_text', '') or matching_rows.iloc[0].get('content', '')
                if review_text:
                    unclassified_reviews.append(review_text)
        
        # 创建"其他问题"类别
        aggregated.append({
            'complaint': '其他问题',
            'count': len(unclassified_ids),
            'reviews': unclassified_reviews,
            'summary': f'包含 {len(unclassified_ids)} 条未明确归类到特定问题类型的负面评论',
            'review_ids': list(unclassified_ids)
        })
        
        # 重新排序（因为添加了新项）
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


def generate_ai_brief(df, negative_ratio):
    """生成 AI 每日简报（基于实际用户反馈数据）"""
    # 确保数据一致性：正面 + 负面 + 中性 = 总数
    negative_count = len(df[df['rating'] < 3])  # rating < 3: 负面
    positive_count = len(df[df['rating'] >= 4])  # rating >= 4: 正面
    neutral_count = len(df[df['rating'] == 3])   # rating == 3: 中性
    
    # 验证数据一致性
    total_calculated = positive_count + negative_count + neutral_count
    if total_calculated != len(df):
        # 如果数据不一致，重新计算（处理可能的 NaN 或其他异常值）
        negative_count = len(df[df['rating'] < 3].dropna())
        positive_count = len(df[df['rating'] >= 4].dropna())
        neutral_count = len(df[df['rating'] == 3].dropna())
    
    # 如果已有分析结果，使用它；否则使用通用描述
    if 'analysis_topics' in st.session_state:
        topics = st.session_state['analysis_topics']
        top_issues = [t.get('topic', '') for t in topics[:3]]
        top_issue_text = "、".join([f"**{issue}**" for issue in top_issues[:2] if issue])
    else:
        top_issue_text = "功能使用问题"
    
    # 构建反馈统计文本（根据是否有中性评价决定显示格式）
    if neutral_count > 0:
        feedback_summary = f"本周共收集 **{len(df)}** 条用户反馈，其中正向评价 **{positive_count}** 条，负向评价 **{negative_count}** 条，中性评价 **{neutral_count}** 条"
    else:
        feedback_summary = f"本周共收集 **{len(df)}** 条用户反馈，其中正向评价 **{positive_count}** 条，负向评价 **{negative_count}** 条"
    
    brief = f"""
### 📊 舆情趋势分析

**整体情绪：** {"😊 正向为主" if negative_ratio < 30 else "😐 中性偏负" if negative_ratio < 50 else "😟 负向预警"}

**核心发现：**
- {feedback_summary}
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
        
        model_config = ConfigDict(use_enum_values=True)
else:
    # 如果没有 Pydantic，使用字典结构
    ActionPlan = dict


def render_case_group(rag_result, action_item, batch_idx=0, item_idx=0):
    """
    成组渲染单个 Case：包含 RAG 归因分析 + 对应的行动建议
    采用 Case-Based 布局，形成完整的证据链闭环
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


def render_rag_card(rag_result, batch_idx=0, item_idx=0):
    """渲染单个 RAG 归因分析卡片"""
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
    elif "用户" in conclusion or "❓" in conclusion or "用户使用问题" in conclusion:
        # 情况 B：用户误解/操作不当
        conclusion_type = "用户误解"
        card_style = "warning"
        title_prefix = "⚠️ [用户误解]"
    elif "✅" in conclusion or "产品已知局限" in conclusion:
        # 情况 C：产品已知局限
        conclusion_type = "产品已知局限"
        card_style = "info"
        title_prefix = "ℹ️ [产品已知局限]"
    else:
        # 其他情况
        conclusion_type = "其他问题"
        card_style = "info"
        title_prefix = "🔵 [其他问题]"
    
    # 提取问题标题
    title_keywords = ["续航", "避障", "云台", "抖动", "电池", "图传", "GPS", "虚标", "硬件", "自检"]
    title = "未知问题"
    for keyword in title_keywords:
        if keyword in review_text:
            title = keyword + "相关问题"
            break
    
    # 生成唯一的 key（避免不同批次间的 key 冲突）
    unique_key = f"rag_{batch_idx}_{item_idx}_{review_id}"
    
    # 使用不同样式展示卡片
    if card_style == "error":
        with st.expander(f"{title_prefix} {title} (ID: {review_id})", expanded=(batch_idx == 0 and item_idx == 0)):
            col_left, col_mid, col_right = st.columns([1, 1, 1])
            
            with col_left:
                st.markdown("##### 💬 用户原话")
                st.error(review_text)
            
            with col_mid:
                st.markdown("##### 📖 RAG 证据")
                if evidence and evidence not in ["未在说明书中找到相关描述", "向量库未初始化，使用基础分析", ""]:
                    if len(evidence) > 500:
                        with st.expander("📄 查看完整证据", expanded=False):
                            st.markdown(evidence)
                        st.error(evidence[:500] + "...")
                    else:
                        st.error(evidence)
                elif evidence == "未在说明书中找到相关描述":
                    st.warning("⚠️ 未在说明书中找到相关描述")
                else:
                    st.warning("⚠️ 向量检索未启用或失败")
            
            with col_right:
                st.markdown("##### 🤖 AI 判定")
                st.error(f"**结论：** {conclusion}")
                st.markdown(f"**分析：** {reason if reason else '暂无详细分析'}")
    elif card_style == "warning":
        with st.expander(f"{title_prefix} {title} (ID: {review_id})", expanded=(batch_idx == 0 and item_idx == 0)):
            col_left, col_mid, col_right = st.columns([1, 1, 1])
            
            with col_left:
                st.markdown("##### 💬 用户原话")
                st.warning(review_text)
            
            with col_mid:
                st.markdown("##### 📖 RAG 证据")
                if evidence and evidence not in ["未在说明书中找到相关描述", "向量库未初始化，使用基础分析", ""]:
                    if len(evidence) > 500:
                        with st.expander("📄 查看完整证据", expanded=False):
                            st.markdown(evidence)
                        st.warning(evidence[:500] + "...")
                    else:
                        st.warning(evidence)
                elif evidence == "未在说明书中找到相关描述":
                    st.info("ℹ️ 未在说明书中找到相关描述")
                else:
                    st.info("ℹ️ 向量检索未启用或失败")
            
            with col_right:
                st.markdown("##### 🤖 AI 判定")
                st.warning(f"**结论：** {conclusion}")
                st.markdown(f"**分析：** {reason if reason else '暂无详细分析'}")
    else:
        with st.expander(f"{title_prefix} {title} (ID: {review_id})", expanded=(batch_idx == 0 and item_idx == 0)):
            col_left, col_mid, col_right = st.columns([1, 1, 1])
            
            with col_left:
                st.markdown("##### 💬 用户原话")
                st.info(review_text)
            
            with col_mid:
                st.markdown("##### 📖 RAG 证据")
                if evidence and evidence not in ["未在说明书中找到相关描述", "向量库未初始化，使用基础分析", ""]:
                    if len(evidence) > 500:
                        with st.expander("📄 查看完整证据", expanded=False):
                            st.markdown(evidence)
                        st.info(evidence[:500] + "...")
                    else:
                        st.info(evidence)
                elif evidence == "未在说明书中找到相关描述":
                    st.info("ℹ️ 未在说明书中找到相关描述")
                else:
                    st.info("ℹ️ 向量检索未启用或失败")
            
            with col_right:
                st.markdown("##### 🤖 AI 判定")
                st.info(f"**结论：** {conclusion}")
                st.markdown(f"**分析：** {reason if reason else '暂无详细分析'}")


def render_action_card(action, batch_idx=0, item_idx=0):
    """渲染单个行动建议卡片"""
    action_type = action.get("action_type", "Jira Ticket")
    title = action.get("title", "")
    content = action.get("content", "")
    priority = action.get("priority", "Medium")
    
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
    
    # 生成唯一的 key（用于其他组件的 key，但 st.expander 不支持 key 参数）
    unique_key = f"action_{batch_idx}_{item_idx}_{action.get('review_id', item_idx)}"
    
    with st.expander(f"{type_icon} **{title}** · {priority_icon} {priority} · {action_type}", expanded=(batch_idx == 0 and item_idx <= 1)):
        st.markdown(f"**优先级：** {priority}")
        st.markdown(f"**类型：** {action_type}")
        st.markdown(f"**内容：**")
        if len(content) > 500:
            st.text_area("", value=content, height=150, disabled=True, key=f"action_content_{unique_key}", label_visibility="collapsed")
        else:
            st.markdown(content)
        
        # Mock 按钮（根据类型使用不同样式）
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
    env_api_key = os.getenv("DASHSCOPE_API_KEY", "")
    default_api_key = env_api_key if env_api_key else ""
    
    # 如果环境变量中有，显示提示；否则允许用户输入
    if env_api_key:
        st.info("✅ 已从环境变量 `DASHSCOPE_API_KEY` 读取 API Key")
        api_key = env_api_key
    else:
        api_key = st.text_input(
            "DashScope API Key (阿里千问)",
            type="password",
            value="",
            placeholder="sk-... 或设置环境变量 DASHSCOPE_API_KEY",
            help="用于 RAG 深度分析功能。推荐方式：在项目根目录创建 .env 文件，添加 DASHSCOPE_API_KEY=your-key"
        )
        
        if api_key:
            st.success("✅ API Key 已配置（临时，仅本次会话有效）")
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

# ==================== 全局状态初始化 (SSOT) ====================
# 检查并初始化 all_reviews（Single Source of Truth）
if 'all_reviews' not in st.session_state:
    # 初始化：从 CSV 文件加载历史数据
    st.session_state.all_reviews = reviews_df.to_dict('records')
    st.session_state.last_run_increment = 0
    # 初始化指标基准值（用于计算增量）
    if len(st.session_state.all_reviews) > 0:
        init_df = pd.DataFrame(st.session_state.all_reviews)
        if 'rating' in init_df.columns:
            init_df['rating'] = pd.to_numeric(init_df['rating'], errors='coerce').fillna(0)
            init_total, init_avg, init_negative = calculate_metrics(init_df)
            st.session_state['prev_total_reviews'] = init_total
            st.session_state['prev_avg_rating'] = init_avg
            st.session_state['prev_negative_ratio'] = init_negative
        else:
            st.session_state['prev_total_reviews'] = 0
            st.session_state['prev_avg_rating'] = 0.0
            st.session_state['prev_negative_ratio'] = 0.0
    else:
        st.session_state['prev_total_reviews'] = 0
        st.session_state['prev_avg_rating'] = 0.0
        st.session_state['prev_negative_ratio'] = 0.0

# 初始化 RAG 分析结果存储
if 'latest_rag_results' not in st.session_state:
    st.session_state.latest_rag_results = []

# 初始化增量巡检相关状态
if 'last_run_time' not in st.session_state:
    st.session_state.last_run_time = None
if 'incremental_rag_results' not in st.session_state:
    st.session_state.incremental_rag_results = []  # 存储本次巡检的RAG结果

# 初始化历史巡检记录（实时风险动态流）
if 'incident_history' not in st.session_state:
    st.session_state.incident_history = []  # 存储所有历史巡检批次

# 检查是否需要刷新页面以更新数据概览
if st.session_state.get('need_refresh', False):
    st.session_state['need_refresh'] = False
    # 延迟刷新，让用户有时间看清工作流完成提示
    time.sleep(2)
    st.rerun()

# ==================== 顶部 Dashboard ====================
# 使用容器统一模块大小
with st.container():
    st.markdown("## 📈 数据概览")
    
    # 计算指标 - 基于 session_state.all_reviews（SSOT）
    all_reviews = st.session_state.get('all_reviews', [])
    
    # 确保 all_reviews 是列表且不为空
    if not all_reviews:
        all_reviews_df = pd.DataFrame(columns=['rating'])
    else:
        # 创建 DataFrame，确保所有评论都被包含
        all_reviews_df = pd.DataFrame(all_reviews)
        
        # 调试：检查数据
        if len(all_reviews_df) > 0:
            # 确保 rating 列存在且为数值类型
            if 'rating' not in all_reviews_df.columns:
                all_reviews_df['rating'] = 0
            else:
                # 确保 rating 是数值类型，处理可能的字符串或其他类型
                all_reviews_df['rating'] = pd.to_numeric(all_reviews_df['rating'], errors='coerce').fillna(0)
            
            # 去重：基于 review_id 去重，避免重复计算
            if 'review_id' in all_reviews_df.columns:
                all_reviews_df = all_reviews_df.drop_duplicates(subset=['review_id'], keep='last')
    
    # 计算指标（强制重新计算，不使用缓存）
    # 重要：每次页面渲染时都重新计算，确保使用最新数据
    total_reviews, avg_rating, negative_ratio = calculate_metrics(all_reviews_df)
    
    # 调试：显示实际数据状态（帮助排查问题，可以临时启用）
    if len(all_reviews_df) > 0 and 'rating' in all_reviews_df.columns:
        rating_series = pd.to_numeric(all_reviews_df['rating'], errors='coerce').dropna()
        if len(rating_series) > 0:
            positive_count = len(rating_series[rating_series >= 4])
            negative_count = len(rating_series[rating_series < 3])
            neutral_count = len(rating_series[(rating_series >= 3) & (rating_series < 4)])
            # 临时调试信息（如果需要可以取消注释）
            # with st.expander("🔍 数据调试信息", expanded=False):
            #     st.write(f"总评论数: {total_reviews}")
            #     st.write(f"正面评论: {positive_count}, 负面评论: {negative_count}, 中性评论: {neutral_count}")
            #     st.write(f"平均评分: {avg_rating:.2f}")
            #     st.write(f"负面占比: {negative_ratio:.2f}%")
            #     st.write(f"评分分布: {rating_series.value_counts().sort_index().to_dict()}")
    
    # 获取上次保存的值（用于计算增量）
    prev_total = st.session_state.get('prev_total_reviews', 0)
    prev_avg = st.session_state.get('prev_avg_rating', 0.0)
    prev_negative_ratio = st.session_state.get('prev_negative_ratio', 0.0)
    
    # 计算 delta 值（只有当有历史数据且总数变化时才计算）
    if prev_total > 0 and prev_total != total_reviews:
        # 总数发生变化，说明有新数据，计算增量
        avg_delta = avg_rating - prev_avg
        negative_delta = negative_ratio - prev_negative_ratio
    elif prev_total == 0:
        # 首次运行，没有历史数据
        avg_delta = None
        negative_delta = None
    else:
        # 总数未变化，但可能数据有更新，仍然计算增量
        avg_delta = avg_rating - prev_avg if prev_avg > 0 else None
        negative_delta = negative_ratio - prev_negative_ratio if prev_negative_ratio > 0 else None
    
    # 保存当前值作为下次的基准（每次都要更新，确保下次计算时使用最新值）
    # 重要：必须在每次渲染时更新，确保下次计算时使用最新值
    st.session_state['prev_total_reviews'] = total_reviews
    st.session_state['prev_avg_rating'] = avg_rating
    st.session_state['prev_negative_ratio'] = negative_ratio
    
    # 三个指标卡片
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # 动态显示增量（基于 last_run_increment）
        delta_text = f"本次新增 {st.session_state.last_run_increment} 条" if st.session_state.last_run_increment > 0 else None
        st.metric(
            label="📝 总评论数",
            value=f"{total_reviews}",
            delta=delta_text,
            delta_color="normal"
        )
    
    with col2:
        # 显示平均评分，带增量变化
        delta_text_avg = f"{avg_delta:+.1f}" if avg_delta is not None and abs(avg_delta) > 0.01 else None
        st.metric(
            label="⭐ 平均评分",
            value=f"{avg_rating:.1f}",
            delta=delta_text_avg,
            delta_color="normal" if avg_delta is None or avg_delta >= 0 else "inverse"
        )
    
    with col3:
        # 显示负面评价占比，带增量变化
        delta_text_negative = f"{negative_delta:+.1f}%" if negative_delta is not None and abs(negative_delta) > 0.01 else None
        st.metric(
            label="😔 负面评价占比",
            value=f"{negative_ratio:.1f}%",
            delta=delta_text_negative,
            delta_color="inverse" if negative_delta is None or negative_delta <= 0 else "normal"
        )

# AI 每日简报 - 使用容器统一大小
with st.container():
    with st.expander("🤖 **AI 每日简报** - 点击展开", expanded=True):
        ai_brief = generate_ai_brief(all_reviews_df, negative_ratio)
        st.markdown(ai_brief)

st.markdown("---")

# ==================== Tab 分页结构 ====================
# 使用容器统一模块大小
with st.container():
    tab_auto, tab_manual = st.tabs(["🛡️ 智能巡检控制台", "🔬 单条归因实验室"])

# ==================== Tab 1: 智能巡检控制台 ====================
with tab_auto:
    st.markdown("### ⚡ 智能工作流")
    st.caption("基于 LangGraph 的自动化巡检系统，自动监控、筛选、分析和生成行动建议")
    
    # 优化按钮布局：左侧按钮，右侧信息
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        workflow_button = st.button("⚡ 运行智能工作流", type="primary", use_container_width=True, key="workflow_btn_auto")
    with col_info:
        # 垂直居中显示上次巡检时间，使用灰色小字
        last_run_time = st.session_state.get('last_run_time', '从未')
        st.markdown(
            f"<div style='padding-top: 10px; color: #6b7280; font-size: 0.9rem;'>🕒 上次自动巡检：{last_run_time}</div>",
            unsafe_allow_html=True
        )
    
    # ==================== 智能工作流执行 ====================
    # Trigger (按钮部分): 只负责运行 Graph，将结果追加到 st.session_state.incident_history
    # 之后立刻调用 st.rerun()，不在这里写任何 st.markdown 或 UI 渲染代码！
    if workflow_button:
        # 检查 API Key
        if not api_key:
            st.error("❌ 请先在侧边栏配置 DashScope API Key")
            st.stop()
        
        try:
            # 导入工作流
            from agent_graph import graph_app
            
            # 记录本次巡检开始时间
            import datetime
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 初始化状态（增量巡检：保留已处理的ID）
            initial_state = {
                "raw_reviews": [],
                "critical_reviews": [],
                "rag_analysis_results": [],
                "action_plans": [],
                "logs": [],
                "processed_ids": st.session_state.get('processed_ids', [])  # 保留历史已处理ID
            }
            
            # 清空本次巡检的结果（只保留历史数据）
            st.session_state.incremental_rag_results = []
            st.session_state.incremental_action_plans = []
            
            # 使用 st.status 展示实时日志（恢复运行过程显示）
            with st.status("🔄 工作流运行中...", expanded=True) as status:
                st.write("🚀 启动智能工作流...")
                
                # 数据同步：使用 stream() 监听流式输出
                final_state = initial_state.copy()
                for event in graph_app.stream(initial_state):
                    # 遍历每个节点的输出
                    for node_name, node_output in event.items():
                        # 合并状态
                        if isinstance(node_output, dict):
                            final_state.update(node_output)
                        
                        # 检测 node_monitor 产出的 raw_reviews
                        if node_name == "monitor" and isinstance(node_output, dict) and "raw_reviews" in node_output:
                            new_reviews = node_output.get("raw_reviews", [])
                            if new_reviews:
                                # 数据同步：立即追加到 session_state.all_reviews（增量累加）
                                st.session_state.all_reviews.extend(new_reviews)
                                st.session_state.last_run_increment = len(new_reviews)
                                st.write(f"📥 数据同步：已添加 {len(new_reviews)} 条新评论到全局状态（累计：{len(st.session_state.all_reviews)} 条）")
                        
                        # 检测 node_rag_analysis 产出的 rag_analysis_results（本次巡检的新增结果）
                        if node_name == "rag_analysis" and isinstance(node_output, dict) and "rag_analysis_results" in node_output:
                            rag_results = node_output.get("rag_analysis_results", [])
                            if rag_results:
                                # 保存本次巡检的RAG结果（增量）
                                st.session_state.incremental_rag_results.extend(rag_results)
                                # 同时更新全局最新结果（用于兼容性）
                                st.session_state.latest_rag_results = rag_results
                                st.write(f"📄 本次巡检发现 {len(rag_results)} 条RAG归因结果（累计：{len(st.session_state.incremental_rag_results)} 条）")
                        
                        # 检测 node_action_gen 产出的 action_plans（本次巡检的新增结果）
                        if node_name == "action_gen" and isinstance(node_output, dict) and "action_plans" in node_output:
                            action_plans = node_output.get("action_plans", [])
                            if action_plans:
                                # 保存本次巡检的行动建议（增量）
                                st.session_state.incremental_action_plans = action_plans
                                st.write(f"💡 本次巡检生成 {len(action_plans)} 条行动建议")
                        
                        # 更新已处理的ID集合（用于幂等性）
                        if isinstance(node_output, dict) and "processed_ids" in node_output:
                            processed_ids = node_output.get("processed_ids", [])
                            if processed_ids:
                                existing_ids = set(st.session_state.get('processed_ids', []))
                                new_ids = set(processed_ids)
                                st.session_state['processed_ids'] = list(existing_ids | new_ids)
                        
                        # 实时显示日志
                        if isinstance(node_output, dict) and "logs" in node_output:
                            logs = node_output.get("logs", [])
                            for log in logs:
                                st.write(log)
                                time.sleep(0.2)  # 模拟实时更新
                
                status.update(label="✅ 工作流执行完成", state="complete")
                st.write("⏳ 正在刷新页面以更新统计数据...")
                time.sleep(1)
            
            # 更新上次巡检时间
            st.session_state.last_run_time = current_time
            
            # ==================== 数据处理：保存到历史记录 ====================
            result = final_state
            rag_results = result.get("rag_analysis_results", [])
            action_plans = result.get("action_plans", [])
            
            # 生成批次记录，插入到历史记录头部（最新的在最上面）
            batch_record = {
                'time': current_time,
                'rag_results': rag_results,
                'actions': action_plans,
                'new_reviews_count': len(final_state.get("raw_reviews", [])),
                'critical_count': len(result.get("critical_reviews", []))
            }
            
            # 插入到头部（Prepend）
            st.session_state.incident_history.insert(0, batch_record)
            
            # 存储结果到 session_state（用于兼容性）
            st.session_state['workflow_result'] = result
            st.session_state['workflow_completed'] = True
            st.session_state['need_refresh'] = True
            
            # 强制清除之前的指标缓存，确保下次计算时使用最新数据
            # 注意：不清除 prev_* 值，因为需要用于计算 delta
            # 但确保 all_reviews 已经更新
            
            # 立即调用 st.rerun() 触发页面刷新，让渲染区域显示新数据
            st.rerun()
            
        except ImportError as e:
            st.error(f"❌ 无法导入工作流模块: {e}")
            st.info("💡 请确保 `agent_graph.py` 文件存在且已正确配置")
        except Exception as e:
            st.error(f"❌ 工作流执行失败: {e}")
            st.exception(e)
    
    # ==================== 持久化渲染区域：实时风险动态流 ====================
    incident_history = st.session_state.get('incident_history', [])
    
    if incident_history:
        st.markdown("---")
        
        # ==================== Part A: 最新动态 (Hero Section) ====================
        latest_batch = incident_history[0]
        latest_rag_results = latest_batch.get('rag_results', [])
        latest_actions = latest_batch.get('actions', [])
        latest_time = latest_batch.get('time', '未知时间')
        latest_new_reviews = latest_batch.get('new_reviews_count', 0)
        
        # 检查是否有 P0 级风险（High 优先级的 Action 或产品缺陷的 RAG）
        has_p0_risk = False
        if latest_actions:
            has_p0_risk = any(action.get('priority') == 'High' for action in latest_actions)
        if not has_p0_risk and latest_rag_results:
            has_p0_risk = any('产品缺陷' in rag.get('conclusion', '') for rag in latest_rag_results)
        
        # 显示标题和统计
        col_title, col_stats = st.columns([2, 1])
        with col_title:
            st.markdown("### 🚨 本次巡检发现 (Latest)")
        with col_stats:
            st.caption(f"📅 {latest_time} · 新增 {latest_new_reviews} 条评论")
        
        # 如果有 P0 级风险，使用 st.error 容器包裹增强警示感
        if has_p0_risk:
            st.error("⚠️ **检测到高风险问题，请立即处理！**")
        
        # Case-Based 成组渲染：通过 review_id 匹配 RAG 和 Action
        if latest_rag_results:
            # 创建 action 字典，以 review_id 为 key，方便查找
            # 支持完整匹配和部分匹配（处理可能的 ID 格式差异）
            action_dict = {}
            for action in latest_actions:
                review_id = action.get('review_id')
                if review_id:
                    action_dict[review_id] = action
                    # 也支持 base_id 匹配（如果 review_id 包含下划线）
                    if '_' in str(review_id):
                        base_id = str(review_id).split('_')[0]
                        if base_id not in action_dict:
                            action_dict[base_id] = action
            
            for item_idx, rag_result in enumerate(latest_rag_results):
                # 通过 review_id 匹配对应的 Action
                review_id = rag_result.get("review_id")
                action_item = None
                
                if review_id:
                    # 优先完整匹配
                    action_item = action_dict.get(review_id)
                    # 如果完整匹配失败，尝试 base_id 匹配
                    if not action_item and '_' in str(review_id):
                        base_id = str(review_id).split('_')[0]
                        action_item = action_dict.get(base_id)
                
                # 如果还是没匹配到，尝试按索引匹配（兜底方案）
                if not action_item and item_idx < len(latest_actions):
                    action_item = latest_actions[item_idx]
                
                # 渲染完整的 Case（RAG + Action 成对）
                render_case_group(rag_result, action_item, batch_idx=0, item_idx=item_idx)
                # Case 之间的分隔
                if item_idx < len(latest_rag_results) - 1:
                    st.markdown("")  # 空白间隔，避免文字粘连
        
        # ==================== Part B: 历史回溯 (Scrollable Container) ====================
        history_batches = incident_history[1:] if len(incident_history) > 1 else []
        
        if history_batches:
            st.divider()  # 分割线，清晰区分最新和历史
            st.markdown("#### 📜 历史巡检记录")
            
            # 使用固定高度的滚动容器
            with st.container(height=500, border=False):
                for batch_idx, batch in enumerate(history_batches, start=1):
                    batch_time = batch.get('time', '未知时间')
                    rag_results = batch.get('rag_results', [])
                    actions = batch.get('actions', [])
                    new_reviews_count = batch.get('new_reviews_count', 0)
                    
                    # 使用 expander 折叠历史批次
                    with st.expander(f"📅 巡检批次: {batch_time} (新增 {new_reviews_count} 条评论)", expanded=False):
                        # Case-Based 成组渲染：通过 review_id 匹配 RAG 和 Action
                        if rag_results:
                            # 创建 action 字典，以 review_id 为 key，方便查找
                            # 支持完整匹配和部分匹配（处理可能的 ID 格式差异）
                            action_dict = {}
                            for action in actions:
                                review_id = action.get('review_id')
                                if review_id:
                                    action_dict[review_id] = action
                                    # 也支持 base_id 匹配（如果 review_id 包含下划线）
                                    if '_' in str(review_id):
                                        base_id = str(review_id).split('_')[0]
                                        if base_id not in action_dict:
                                            action_dict[base_id] = action
                            
                            for item_idx, rag_result in enumerate(rag_results):
                                # 通过 review_id 匹配对应的 Action
                                review_id = rag_result.get("review_id")
                                action_item = None
                                
                                if review_id:
                                    # 优先完整匹配
                                    action_item = action_dict.get(review_id)
                                    # 如果完整匹配失败，尝试 base_id 匹配
                                    if not action_item and '_' in str(review_id):
                                        base_id = str(review_id).split('_')[0]
                                        action_item = action_dict.get(base_id)
                                
                                # 如果还是没匹配到，尝试按索引匹配（兜底方案）
                                if not action_item and item_idx < len(actions):
                                    action_item = actions[item_idx]
                                
                                # 渲染完整的 Case（RAG + Action 成对）
                                render_case_group(rag_result, action_item, batch_idx=batch_idx, item_idx=item_idx)
                                # Case 之间的分隔
                                if item_idx < len(rag_results) - 1:
                                    st.markdown("")  # 空白间隔，避免文字粘连
                        
                        # 批次之间的分隔
                        if batch_idx < len(history_batches):
                            st.markdown("")
    else:
        # 如果工作流未运行，显示提示
        st.info("👆 点击上方「运行智能工作流」按钮，开始首次增量巡检")

# ==================== Tab 2: 单条归因实验室 ====================
with tab_manual:
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
                        import random
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

# ===== 保留原有的批量分析功能（用于兼容性，但不在 Tab 中显示） =====
# 注意：这部分代码保留在全局，但不会在 UI 中显示，仅用于内部状态管理
# 已禁用的代码块（已移到 Tab 中）
# 注意：批量分析功能已移除，现在只在 Tab 中提供单条评论分析功能

# ==================== 清理：删除全局重复的 Action 区 ====================
# 注意：Action 建议现在只在各自的 Tab 中显示，不再在全局显示

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

