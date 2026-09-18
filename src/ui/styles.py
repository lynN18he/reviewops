"""
UI 样式管理模块
集中管理所有 CSS 样式和页面配置
"""

import streamlit as st


def apply_page_config():
    """应用页面配置"""
    st.set_page_config(
        page_title="ReviewOps · B2B SaaS 研发智能问诊中台",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded"
    )


def apply_custom_styles():
    """应用自定义 CSS 样式"""
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
        
        /* 指标卡片样式 - 紧凑；四卡统一高度避免「只有总数卡变矮」 */
        [data-testid="stMetric"] {
            background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
            padding: 0.75rem 1rem;
            border-radius: 10px;
            border: 1px solid rgba(99, 102, 241, 0.3);
            box-shadow: 0 4px 20px rgba(99, 102, 241, 0.15);
            min-height: 6.35rem;
            box-sizing: border-box;
        }
        
        [data-testid="stMetric"] label {
            color: #a5b4fc !important;
            font-weight: 500;
        }
        
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #e0e7ff !important;
            font-weight: 700;
        }

        /* 环比/副行：主题「off」灰字 + 低 opacity 在深底上几乎看不见，强制不透明并略提亮默认字色 */
        [data-testid="stMetric"] [data-testid="stMetricDelta"] {
            opacity: 1 !important;
            font-size: 0.82rem !important;
            font-weight: 500 !important;
        }
        [data-testid="stMetric"] [data-testid="stMetricDelta"] * {
            opacity: 1 !important;
        }
        [data-testid="stMetric"] [data-testid="stMetricDelta"] svg,
        [data-testid="stMetric"] [data-testid="stMetricDelta"] path {
            opacity: 1 !important;
        }
        
        /* st.metric 的 help：原生多为浅灰小圆，叠在深蓝渐变上几乎看不见 —— 强制高对比 */
        [data-testid="stMetric"] button {
            color: #f8fafc !important;
            background: rgba(255, 255, 255, 0.14) !important;
            border: 1px solid rgba(226, 232, 240, 0.55) !important;
            opacity: 1 !important;
        }
        [data-testid="stMetric"] button:hover {
            background: rgba(255, 255, 255, 0.26) !important;
            border-color: #e0e7ff !important;
        }
        [data-testid="stMetric"] button svg,
        [data-testid="stMetric"] button path {
            fill: #f8fafc !important;
            opacity: 1 !important;
        }
        [data-testid="stMetric"] [data-testid="stTooltipIcon"] {
            color: #f8fafc !important;
        }
        [data-testid="stMetric"] a[href="#"],
        [data-testid="stMetric"] [data-testid="stMetricLabel"] svg,
        [data-testid="stMetric"] [data-testid="stMetricLabel"] path {
            color: #f8fafc !important;
            fill: #f8fafc !important;
            opacity: 1 !important;
        }
        
        /* 侧栏：品牌底色 + 侧栏内 Markdown 标题可读（信息卡以内联 HTML 为准） */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%) !important;
            padding: 0.5rem 0.65rem !important;
            border-right: 1px solid #334155 !important;
        }
        [data-testid="stSidebar"] .stMarkdown h2,
        [data-testid="stSidebar"] .stMarkdown h3 {
            color: #f8fafc !important;
        }
        [data-testid="stSidebar"] .stCaption,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
            color: #cbd5e1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stRadio"] label,
        [data-testid="stSidebar"] [data-testid="stRadio"] label span {
            color: #f1f5f9 !important;
        }
        /* 侧边栏导航单选：radiogroup 内段落常为实际可见文案，强制亮白 */
        [data-testid="stSidebar"] div[role="radiogroup"] p {
            color: #f8fafc !important;
            font-size: 15px !important;
        }

        /* 按钮样式 - 主按钮 */
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
        
        /* 批次 CTA 按钮 - 强制次级样式（白底黑字），消灭紫薯精 */
        [data-testid="stExpander"] .stButton > button {
            background: #ffffff !important;
            color: #374151 !important;
            border: 1px solid #d1d5db !important;
            box-shadow: none !important;
        }
        [data-testid="stExpander"] .stButton > button:hover {
            background: #f9fafb !important;
            border-color: #9ca3af !important;
            transform: none;
            box-shadow: none !important;
        }
        
        /* 工单卡片辅助按钮（一键复制回复）- 强制白底灰边，绝不紫色 */
        [data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton > button {
            background: #ffffff !important;
            color: #374151 !important;
            border: 1px solid #d1d5db !important;
            box-shadow: none !important;
        }
        [data-testid="stHorizontalBlock"] > div:nth-child(2) .stButton > button:hover {
            background: #f9fafb !important;
            border-color: #9ca3af !important;
            transform: none;
            box-shadow: none !important;
        }
        
        /* 表格样式 */
        .stDataFrame {
            border-radius: 12px;
            overflow: hidden;
        }
        
        /* st.table（如研发疑难队列）：单元格内换行，避免长段落在同一行横滑 */
        [data-testid="stTable"] td,
        [data-testid="stTable"] th {
            white-space: pre-wrap !important;
            word-break: break-word;
            vertical-align: top;
            max-width: 42vw;
        }
        
        /* Expander 样式 - 中性边框，避免安全批次出现红色视觉污染 */
        [data-testid="stExpander"] {
            border: 1px solid rgba(148, 163, 184, 0.3) !important;
            border-radius: 8px;
            background: transparent !important;
        }
        .streamlit-expanderHeader {
            background: rgba(148, 163, 184, 0.08) !important;
            border-radius: 8px;
        }
        
        /* 模块间留白（替代 hr ---） */
        .ro-section-gap {
            height: 1.75rem;
            min-height: 1.75rem;
            margin: 0;
            padding: 0;
        }
        .ro-vspace-md {
            height: 1rem;
            margin: 0;
            padding: 0;
        }
        /*
         * 页脚：固定在视口底部；left 与侧栏宽度对齐（展开约 21rem），窄屏铺满。
         */
        [data-testid="stAppViewContainer"] .main .block-container {
            padding-bottom: 4.25rem !important;
        }
        .ro-page-footer-muted {
            position: fixed !important;
            left: 21rem;
            right: 0;
            bottom: 0;
            z-index: 998;
            margin: 0 !important;
            padding: 0.55rem 1.5rem 0.75rem;
            box-sizing: border-box;
            border-top: 1px solid rgba(148, 163, 184, 0.2);
            background: rgba(255, 255, 255, 0.94);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
        }
        @media (max-width: 768px) {
            .ro-page-footer-muted {
                left: 0 !important;
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }
        }
        @media (prefers-color-scheme: dark) {
            .ro-page-footer-muted {
                background: rgba(15, 23, 42, 0.92);
                border-top-color: rgba(148, 163, 184, 0.15);
            }
            .ro-page-footer-muted p {
                color: rgba(148, 163, 184, 0.65) !important;
            }
        }
        .ro-page-footer-muted p {
            margin: 0.1rem 0 !important;
            font-size: 0.6875rem !important;
            line-height: 1.35 !important;
            color: rgba(100, 116, 139, 0.72) !important;
            letter-spacing: 0.03em;
        }
        /* 主标题：渐变字 + 大号字重（SaaS 品牌冲击力） */
        [data-testid="stAppViewContainer"] .stMarkdown h1 {
            font-size: 2.25rem !important;
            font-weight: 800 !important;
            letter-spacing: -0.03em;
            margin: 0 0 0.2rem 0 !important;
            line-height: 1.15 !important;
            background: linear-gradient(90deg, #6366f1, #8b5cf6, #06b6d4);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        [data-testid="stAppViewContainer"] .stMarkdown h5 {
            color: #94a3b8 !important;
            font-weight: 500 !important;
            font-size: 0.95rem !important;
            margin: 0 0 0.35rem 0 !important;
            line-height: 1.4 !important;
        }
        [data-testid="stAppViewContainer"] .stMarkdown h2 {
            font-size: 1.2rem !important;
            font-weight: 600 !important;
            letter-spacing: -0.01em;
            margin: 0.15rem 0 0.6rem 0 !important;
            line-height: 1.3 !important;
        }
        [data-testid="stAppViewContainer"] .stMarkdown h3 {
            font-size: 1.02rem !important;
            font-weight: 600 !important;
            margin: 0.65rem 0 0.35rem 0 !important;
            line-height: 1.35 !important;
        }
        [data-testid="stAppViewContainer"] .stMarkdown h4 { font-size: 0.98rem !important; }
        [data-testid="stAppViewContainer"] .stMarkdown h5 { font-size: 0.92rem !important; }
        [data-testid="stAppViewContainer"] .stMarkdown p,
        [data-testid="stAppViewContainer"] .stMarkdown {
            font-size: 0.9rem !important;
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
        
        /* 分割线 - 紧凑 */
        hr {
            border: none;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.5), transparent);
            margin: 1rem 0;
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

