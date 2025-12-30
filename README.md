# ReviewOps - 用户反馈决策中台

一个基于 RAG + LLM 的 B端 SaaS 原型，帮助产品经理分析用户反馈并生成可执行的行动建议。

## ✨ 功能特性

- **智能语义聚类**：使用 LLM 自动发现用户反馈中的主要抱怨点
- **RAG 归因分析**：基于产品说明书进行智能归因，识别问题根源
- **动态行动生成**：根据 RAG 分析结果自动生成针对性的行动计划
- **增量巡检架构**：支持定时任务和手动触发的增量数据同步
- **Mock 工作流集成**：模拟真实的工作流集成（Jira、Notion、Email 等）

## 🚀 快速开始

### 环境要求

- Python 3.8+
- DashScope API Key (阿里云千问)

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置 API Key

**推荐方式（使用 .env 文件）**：

1. 复制 `.env.example` 为 `.env`：
   ```bash
   cp .env.example .env
   ```

2. 编辑 `.env` 文件，填入你的 API Key：
   ```bash
   DASHSCOPE_API_KEY=your-dashscope-api-key-here
   ```

**备选方式（环境变量）**：

```bash
export DASHSCOPE_API_KEY="your-dashscope-api-key"
```

**获取 API Key**：
1. 访问 https://dashscope.console.aliyun.com/
2. 注册/登录阿里云账号
3. 在 API-KEY 管理页面创建新的 API Key

> 💡 **提示**：`.env` 文件已在 `.gitignore` 中，不会被提交到 Git，可以安全地存储你的 API Key。

### 构建知识库

首先运行数据摄入脚本，将产品说明书向量化：

```bash
python injest.py
```

这将：
- 读取 `dji_spec.pdf`（产品说明书）
- 进行文档切分和向量化
- 保存到 `./chroma_db` 目录

### 启动应用

```bash
streamlit run app.py
```

应用将在 http://localhost:8501 启动

## 📁 项目结构

```
reviewops/
├── src/                      # 核心业务逻辑模块
│   ├── __init__.py
│   ├── config.py            # 配置管理（集中管理所有配置参数）
│   ├── state.py             # 状态定义（ReviewState 和 reducer）
│   ├── utils.py             # 工具函数（LLM 初始化等）
│   ├── graph.py             # 工作流图构建（LangGraph 组装）
│   └── nodes/                # 工作流节点模块
│       ├── __init__.py
│       ├── monitor.py       # 监控节点（数据生成）
│       ├── filter.py        # 筛选节点（高危评论筛选）
│       ├── rag.py           # RAG 分析节点（归因分析）
│       └── action.py        # 行动生成节点
├── app.py                   # Streamlit UI（仅保留界面渲染逻辑）
├── injest.py                # 数据摄入脚本
├── requirements.txt         # Python 依赖
├── user_reviews.csv         # 用户评论数据
├── dji_spec.pdf             # 产品说明书（PDF）
├── chroma_db/               # 向量数据库（自动生成，已忽略）
└── README.md                # 项目说明
```

## ⚙️ 配置管理

所有配置参数集中在 `src/config.py` 中管理，支持通过环境变量覆盖默认值：

### LLM 配置

```bash
# .env 文件
LLM_MODEL=qwen-plus              # LLM 模型名称
LLM_TEMPERATURE=0                # 温度参数（0-1）
```

### Embedding 配置

```bash
EMBEDDING_MODEL=text-embedding-v3  # Embedding 模型名称
```

### 向量数据库配置

```bash
VECTOR_DB_PATH=./chroma_db         # 向量数据库路径
RAG_TOP_K=5                        # RAG 检索文档数量
RAG_DISTANCE_THRESHOLD=1.5         # 距离阈值
RAG_MAX_CONTEXT_LENGTH=300         # 每个文档的最大长度
RAG_MAX_DOCS_IN_CONTEXT=3         # 上下文中的最大文档数
```

### 筛选节点配置

```bash
FILTER_RATING_THRESHOLD=3          # 高危评论评分阈值（低于此评分为高危）
```

### 监控节点配置

```bash
MONITOR_MIN_REVIEWS=2              # 每批最少评论数
MONITOR_MUST_HAVE_POSITIVE=true    # 是否必须包含正面评论
```

### 行动生成配置

```bash
ACTION_DEFAULT_TYPE=Jira Ticket    # 默认行动类型
ACTION_DEFAULT_PRIORITY=Medium     # 默认优先级
```

## 🔧 技术栈

- **前端框架**：Streamlit
- **数据处理**：Pandas
- **可视化**：Plotly
- **工作流引擎**：LangGraph
- **RAG 框架**：LangChain
- **向量数据库**：ChromaDB
- **Embedding 模型**：阿里云 DashScope (text-embedding-v3)
- **LLM 模型**：阿里云千问 (qwen-plus)

## 📊 核心功能

### 1. 数据概览
- 总评论数、平均评分、负面评价占比
- AI 每日简报
- 增量数据统计

### 2. 智能巡检控制台
- **增量巡检架构**：每次运行视为新的增量同步，数据累加而非重置
- **实时工作流**：基于 LangGraph 的智能工作流执行
- **RAG 归因分析**：自动提取负面评价，基于产品说明书进行 RAG 检索和归因
- **动态行动生成**：根据 RAG 归因结论自动生成行动计划
- **历史记录管理**：Hero + History 分层展示，最新结果直接展示，历史记录可折叠查看

### 3. 行动建议类型
支持多种行动类型：
- 🐞 **Jira Ticket**（产品缺陷）
- 📝 **Doc Update**（文档更新）
- 📧 **Email Draft**（客服邮件）
- 📅 **Meeting**（会议安排）

按优先级自动排序（High / Medium / Low）

## 🏗️ 架构设计

### 模块化设计

项目采用模块化架构，职责清晰：

- **`src/state.py`**：定义工作流状态结构和状态合并逻辑
- **`src/config.py`**：集中管理所有配置参数，支持环境变量覆盖
- **`src/utils.py`**：工具函数（LLM 初始化等）
- **`src/graph.py`**：工作流图构建和路由逻辑
- **`src/nodes/`**：各个工作流节点的实现
  - `monitor.py`：数据监控和生成
  - `filter.py`：高危评论筛选
  - `rag.py`：RAG 归因分析
  - `action.py`：行动建议生成
- **`app.py`**：仅包含 Streamlit UI 渲染逻辑

### 增量巡检架构

- **幂等性保证**：通过 `processed_ids` 避免重复处理
- **数据累加**：每次运行将新数据追加到全局状态
- **历史记录**：所有巡检批次保存在 `incident_history` 中
- **实时反馈**：工作流执行过程实时显示

## 🔒 安全提示

⚠️ **重要**：在提交代码到 GitHub 之前，请确保：

1. 移除所有硬编码的 API Key
2. 使用环境变量或 `.env` 文件管理敏感信息
3. 将 `.env` 添加到 `.gitignore`

## 📝 使用说明

### 1. 准备数据
- 将用户评论数据放入 `user_reviews.csv`
- 将产品说明书 PDF 放入项目根目录

### 2. 构建知识库
```bash
python injest.py
```

### 3. 启动应用
```bash
streamlit run app.py
```

### 4. 使用流程

#### 智能巡检控制台（增量模式）

1. **配置 API Key**：在侧边栏输入 DashScope API Key
2. **运行工作流**：点击"⚡ 运行智能工作流"按钮
3. **查看结果**：
   - **Hero Section**：最新巡检结果直接展示
   - **History Section**：历史巡检记录可折叠查看
4. **数据概览**：顶部 Dashboard 实时更新统计数据
5. **查看行动建议**：每个归因结果对应一个行动建议，可点击按钮执行操作

#### 手动分析模式

1. 在侧边栏配置 API Key
2. 点击"开始归因分析"
3. 查看 RAG 分析结果
4. 查看自动生成的行动建议
5. 点击按钮执行相应操作

## 🧪 开发指南

### 添加新节点

1. 在 `src/nodes/` 目录下创建新文件，例如 `custom_node.py`
2. 实现节点函数，接受 `ReviewState` 并返回 `ReviewState`
3. 在 `src/graph.py` 中导入并添加到工作流图

### 修改配置

所有配置参数在 `src/config.py` 中集中管理，支持：
- 代码中直接修改默认值
- 通过环境变量覆盖（推荐用于不同环境）

### 扩展功能

- **新增行动类型**：修改 `src/nodes/action.py` 中的 prompt
- **调整筛选规则**：修改 `src/config.py` 中的 `FilterConfig.KEYWORDS`
- **优化 RAG 检索**：调整 `VectorStoreConfig` 中的参数

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License
