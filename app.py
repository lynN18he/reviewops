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

# 初始化 RAG 分析结果存储
if 'latest_rag_results' not in st.session_state:
    st.session_state.latest_rag_results = []

# 检查是否需要延迟刷新页面（让用户先看到工作流结果）
if st.session_state.get('need_refresh', False):
    st.session_state['need_refresh'] = False
    # 延迟刷新，让用户有时间看清完成提示
    time.sleep(1)
    st.rerun()

# ==================== 顶部 Dashboard ====================
st.markdown("## 📈 数据概览")

# 计算指标 - 基于 session_state.all_reviews（SSOT）
all_reviews_df = pd.DataFrame(st.session_state.all_reviews)
total_reviews, avg_rating, negative_ratio = calculate_metrics(all_reviews_df)

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
    ai_brief = generate_ai_brief(all_reviews_df, negative_ratio)
    st.markdown(ai_brief)

st.markdown("---")

# ==================== 智能工作流区 ====================
st.markdown("## ⚡ 智能工作流")
st.caption("基于 LangGraph 的自动化巡检系统，自动监控、筛选、分析和生成行动建议")

# 工作流按钮
col_workflow, col_manual, col_space = st.columns([1, 1, 2])
with col_workflow:
    workflow_button = st.button("⚡ 运行智能工作流", use_container_width=True, type="primary")
with col_manual:
    analyze_button = st.button("🚀 手动归因分析", use_container_width=True)

# ==================== 智能工作流执行 ====================
if workflow_button:
    # 检查 API Key
    if not api_key:
        st.error("❌ 请先在侧边栏配置 DashScope API Key")
        st.stop()
    
    try:
        # 导入工作流
        from agent_graph import graph_app
        
        # 初始化状态
        initial_state = {
            "raw_reviews": [],
            "critical_reviews": [],
            "rag_analysis_results": [],
            "action_plans": [],
            "logs": []
        }
        
        # 使用 st.status 展示实时日志
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
                            # 数据同步：立即追加到 session_state.all_reviews
                            st.session_state.all_reviews.extend(new_reviews)
                            st.session_state.last_run_increment = len(new_reviews)
                            st.write(f"📥 数据同步：已添加 {len(new_reviews)} 条新评论到全局状态")
                    
                    # 检测 node_rag_analysis 产出的 rag_analysis_results
                    if node_name == "rag_analysis" and isinstance(node_output, dict) and "rag_analysis_results" in node_output:
                        rag_results = node_output.get("rag_analysis_results", [])
                        if rag_results:
                            # 保存 RAG 分析结果到 session_state，防止页面刷新后丢失
                            st.session_state.latest_rag_results = rag_results
                            st.write(f"📄 RAG 分析结果已保存：{len(rag_results)} 条")
                    
                    # 实时显示日志
                    if isinstance(node_output, dict) and "logs" in node_output:
                        logs = node_output.get("logs", [])
                        for log in logs:
                            st.write(log)
                            time.sleep(0.2)  # 模拟实时更新
            
            status.update(label="✅ 工作流执行完成", state="complete")
            
            # 强制刷新：在工作流运行完毕、日志显示"✅ 完成"后，添加延迟然后刷新
            st.write("⏳ 正在刷新页面以更新统计数据...")
            time.sleep(1)
            
            # 标记需要刷新，但不在这里直接调用 st.rerun()（因为还在 status 容器内）
            st.session_state['need_refresh'] = True
        
        # 显示结果摘要
        st.success(f"✅ 工作流执行完成！")
        
        # 使用最终状态
        result = final_state
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📥 新评论", len(result.get("raw_reviews", [])))
        with col2:
            st.metric("🔍 高危评论", len(result.get("critical_reviews", [])))
        with col3:
            st.metric("📄 归因结果", len(result.get("rag_analysis_results", [])))
        with col4:
            st.metric("💡 行动建议", len(result.get("action_plans", [])))
        
        # 显示行动建议卡片
        action_plans = result.get("action_plans", [])
        if action_plans:
            st.markdown("---")
            st.markdown("### 💡 生成的行动建议")
            
            # 按优先级排序
            priority_order = {"High": 3, "Medium": 2, "Low": 1}
            sorted_actions = sorted(
                action_plans,
                key=lambda x: (priority_order.get(x.get("priority", "Medium"), 2), x.get("title", "")),
                reverse=True
            )
            
            for idx, action in enumerate(sorted_actions, 1):
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
                
                with st.expander(f"{type_icon} **{title}** · {priority_icon} {priority} · {action_type}", expanded=(idx <= 2)):
                    st.markdown(f"**优先级：** {priority}")
                    st.markdown(f"**类型：** {action_type}")
                    st.markdown(f"**内容：**")
                    if len(content) > 500:
                        st.text_area("", value=content, height=150, disabled=True, key=f"action_content_{idx}", label_visibility="collapsed")
                    else:
                        st.markdown(content)
                    
                    # Mock 按钮
                    if action_type == "Jira Ticket":
                        if st.button("🚀 推送至 Jira", key=f"workflow_jira_{idx}", use_container_width=True):
                            ticket_id = f"DJI-2025-{1000 + idx}"
                            st.toast(f"✅ 工单已创建！Ticket ID: {ticket_id}", icon="🎉")
                    elif action_type == "Doc Update":
                        if st.button("📝 创建 Notion Task", key=f"workflow_notion_{idx}", use_container_width=True):
                            st.toast("✅ Notion 任务已创建！", icon="🎉")
                    elif action_type == "Email Draft":
                        if st.button("📧 复制邮件", key=f"workflow_email_{idx}", use_container_width=True):
                            st.toast("✅ 邮件内容已复制到剪贴板！", icon="🎉")
                    elif action_type == "Meeting":
                        if st.button("📅 创建会议", key=f"workflow_meeting_{idx}", use_container_width=True):
                            st.toast("✅ 会议已创建！", icon="🎉")
        
        # 存储结果到 session_state
        st.session_state['workflow_result'] = result
        st.session_state['workflow_completed'] = True
        
        # 标记需要刷新页面（但不立即刷新，让用户先看到结果）
        st.session_state['need_refresh'] = True
        
    except ImportError as e:
        st.error(f"❌ 无法导入工作流模块: {e}")
        st.info("💡 请确保 `agent_graph.py` 文件存在且已正确配置")
    except Exception as e:
        st.error(f"❌ 工作流执行失败: {e}")
        st.exception(e)

# ==================== 中间核心区：RAG 分析 ====================
st.markdown("## 🔍 RAG 归因分析")
st.caption("基于产品说明书对用户反馈进行智能归因，识别问题根源")

# 显示工作流生成的 RAG 分析结果
workflow_rag_results = st.session_state.get('latest_rag_results', [])
if workflow_rag_results:
    st.info(f"📊 工作流已生成 {len(workflow_rag_results)} 条 RAG 归因分析结果")
    
    for idx, rag_result in enumerate(workflow_rag_results, 1):
        review_id = rag_result.get("review_id", f"未知_{idx}")
        review_text = rag_result.get("review_text", "")
        conclusion = rag_result.get("conclusion", "❓ 需要人工判断")
        reason = rag_result.get("reason", "")
        
        # 根据结论类型设置颜色和图标
        if "✅" in conclusion or "产品已知局限" in conclusion:
            color = "🟢"
            conclusion_type = "产品已知局限"
        elif "⚠️" in conclusion or "需进一步调查" in conclusion:
            color = "🟡"
            conclusion_type = "需进一步调查"
        else:
            color = "🔵"
            conclusion_type = "用户使用问题"
        
        # 提取问题标题（从评论中提取关键词）
        title_keywords = ["续航", "避障", "云台", "抖动", "电池", "图传", "GPS", "虚标"]
        title = "未知问题"
        for keyword in title_keywords:
            if keyword in review_text:
                title = keyword + "相关问题"
                break
        
        with st.expander(f"{color} **{conclusion_type}** · {title} (ID: {review_id})", expanded=(idx == 1)):
            col_left, col_mid, col_right = st.columns([1, 1, 1])
            
            with col_left:
                st.markdown("##### 💬 用户原话")
                st.info(review_text)
            
            with col_mid:
                st.markdown("##### 📖 RAG 证据")
                # 这里暂时显示占位文本，后续可以接入真实的向量检索结果
                st.warning("⚠️ 当前使用基础 RAG 逻辑，未接入向量检索。\n\n后续版本将显示从产品说明书中检索到的相关证据片段。")
            
            with col_right:
                st.markdown("##### 🤖 AI 判定")
                st.markdown(f"**结论：** {conclusion}")
                st.markdown(f"**分析：** {reason if reason else '暂无详细分析'}")
        
        if idx < len(workflow_rag_results):
            st.divider()
elif st.session_state.get('workflow_completed', False):
    st.info("💡 工作流已完成，但未生成 RAG 分析结果（可能因为无高危评论）")

st.markdown("---")

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
        # 存储负面评论总数，供后续显示使用
        st.session_state['total_negative_reviews'] = len(negative_reviews)
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
    
    # 获取总负面评论数，用于计算百分比
    total_negative_count = st.session_state.get('total_negative_reviews', sum(agg['count'] for agg in sorted_complaints))
    
    with col_chart:
        # 计算每个问题的百分比（基于总负面评论数，而不是去重后的数量）
        complaint_counts_with_pct = complaint_counts.copy()
        complaint_counts_with_pct['百分比'] = (complaint_counts_with_pct['出现次数'] / total_negative_count * 100).round(1)
        
        # 计算每个问题的百分比（基于总负面评论数）
        custom_percentages = []
        for idx, row in complaint_counts_with_pct.iterrows():
            pct = row['百分比']
            custom_percentages.append(pct)
        
        # 创建可交互的饼图
        # 使用 texttemplate 来显示标签和基于总负面评论数的百分比
        fig = go.Figure(data=[go.Pie(
            labels=complaint_counts['问题类型'],
            values=complaint_counts['出现次数'],
            hole=0.4,  # 甜甜圈样式
            marker=dict(
                colors=colors,
                line=dict(color='#ffffff', width=2)
            ),
            texttemplate='%{label}<br>%{text}',  # 自定义文本模板：显示标签和百分比
            text=[f"{pct:.1f}%" for pct in custom_percentages],  # 显示基于总负面评论数的百分比
            textposition='outside',
            textfont=dict(size=12),
            hovertemplate="<b>%{label}</b><br>出现次数: %{value}<br>占比: %{customdata:.1f}%<extra></extra>",
            customdata=custom_percentages,  # 传递百分比数据用于 hover
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
                    text=f"<b>{len(sorted_complaints)}</b><br>类负面评论",
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
        
        # 严重程度指示器 - 使用总负面评论数
        total_negative_count = st.session_state.get('total_negative_reviews', sum(agg['count'] for agg in sorted_complaints))
        severity_pct = top_count / total_negative_count * 100 if total_negative_count > 0 else 0
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
            total_negative_count = st.session_state.get('total_negative_reviews', sum(agg['count'] for agg in sorted_complaints))
            for agg in sorted_complaints[1:]:
                pct = agg['count'] / total_negative_count * 100 if total_negative_count > 0 else 0
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
        # 使用实际的负面评论总数
        total_review_count = st.session_state.get('total_negative_reviews', sum(agg['count'] for agg in aggregated_complaints))
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
                
                # 如果有源文档，显示证据来源（显示所有相关证据，不限制数量）
                if source_docs:
                    st.markdown("")
                    with st.expander(f"📚 检索到的证据来源 ({len(source_docs)} 条)", expanded=False):
                        for i, doc in enumerate(source_docs, 1):
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
                            if i < len(source_docs):
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

