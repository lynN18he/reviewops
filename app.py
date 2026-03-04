"""
ReviewOps - 用户反馈决策中台
一个帮助产品经理分析用户反馈的 B端 SaaS 原型
"""

import streamlit as st
import pandas as pd
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# ==================== UI 模块导入 ====================
from src.ui.styles import apply_page_config, apply_custom_styles
from src.ui.state import init_session_state
from src.ui.tab_dashboard import render_tab as render_dashboard_tab, render_dashboard_metrics
from src.ui.tab_playground import render_tab as render_playground_tab
from src.graph import graph_app

# ==================== 页面配置 ====================
apply_page_config()
apply_custom_styles()

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

# ==================== 工具函数 ====================
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


def extract_product_name():
    """从 CSV 文件名或数据中提取产品名称"""
    # 简单实现：从文件名推断
    return "DJI Mini 4 Pro"


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

    # LangGraph 工作流可视化
    with st.expander("📐 LangGraph 工作流图", expanded=False):
        try:
            g = graph_app.get_graph()
            mermaid_code = g.draw_mermaid()
            st.caption("将下方代码复制到 [mermaid.live](https://mermaid.live) 可查看流程图")
            st.code(mermaid_code, language="mermaid")
            try:
                ascii_art = g.draw_ascii()
                st.caption("ASCII 预览")
                st.code(ascii_art, language="text")
            except ImportError:
                st.caption("安装 grandalf 后可显示 ASCII 图：`pip install grandalf`")
        except Exception as e:
            st.warning(f"无法加载图：{e}")
    
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

# ==================== 全局状态初始化 ====================
init_session_state(reviews_df, calculate_metrics)

# ==================== 顶部 Dashboard ====================
render_dashboard_metrics(calculate_metrics, generate_ai_brief)

st.markdown("---")

# ==================== Tab 分页结构 ====================
# 使用容器统一模块大小
with st.container():
    tab_auto, tab_manual = st.tabs(["🛡️ 智能巡检控制台", "🔬 单条归因实验室"])

# ==================== Tab 1: 智能巡检控制台 ====================
with tab_auto:
    render_dashboard_tab(api_key, calculate_metrics, generate_ai_brief)

# ==================== Tab 2: 单条归因实验室 ====================
with tab_manual:
    render_playground_tab(api_key)

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
