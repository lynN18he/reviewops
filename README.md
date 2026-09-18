# ReviewOps - B2B SaaS 研发智能问诊中台

一个基于 RAG + LLM 的 B 端 SaaS 原型，帮助支持团队与产品经理分析客诉工单、归因问题并生成可执行的行动建议。

## ✨ 功能特性

- **LangGraph 智能巡检**：Monitor → Filter → RAG → Agent 诊断路由 → 行动生成（Email / Jira / Escalate）
- **RAG 归因分析**：基于 `saas_knowledge.txt` 知识库（SOP、已知缺陷、发版说明）进行按 `doc_type` 约束的 Tool 检索与归因
- **晨会数据大盘**：黄金三指标（AI 闭环率、疑难升级率、缺陷识别率）+ LLM 动态晨报 + 工单工作台
- **增量批次巡检**：按 `Batch_ID` 顺序从 `incremental_tickets.csv` 逐批拉取，支持演示「定时/按需同步」
- **单票实验室**：单条客诉 Dry-run 归因，可选写入正式库
- **SQLite 持久化**：工单、分析结果、巡检游标与批次流水账写入 `reviewops.db`，支持基线预热与增量累加

## 🚀 快速开始

### 环境要求

- Python 3.8+
- DashScope API Key（阿里云千问）

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

2. 编辑 `.env`，填入 API Key：
   ```bash
   DASHSCOPE_API_KEY=your-dashscope-api-key-here
   ```

**获取 API Key**：访问 [DashScope 控制台](https://dashscope.console.aliyun.com/) → API-KEY 管理。

> `.env` 已在 `.gitignore` 中，不会被提交到 Git。

### 构建知识库

```bash
python injest.py
```

读取 `saas_knowledge.txt`，切分并向量化，写入仓库根目录下的 `chroma_db/`（路径与启动 cwd 无关，见 `src/config.py`）。

### 预热冷启动基线（推荐）

首次演示前，建议对冷启动工单跑一遍完整 LLM 分析，写入大盘基线：

```bash
python seed_db.py
```

该脚本会：预检向量库 → 清空 `tickets` 表 → 对 `cold_start_tickets.csv` 全量跑 LangGraph → 写入 `rag_result` / `action_plan`。

> 修改 Prompt、RAG 阈值或知识库后，需重新 `python injest.py` 并 `python seed_db.py`，否则大盘仍是旧分析结果。

### 启动应用

```bash
streamlit run app.py
```

浏览器打开 http://localhost:8501

## 📁 项目结构

```
reviewops/
├── src/
│   ├── config.py              # 配置（LLM / RAG / Monitor / 路径解析）
│   ├── state.py               # LangGraph 状态定义
│   ├── graph.py               # 工作流图组装
│   ├── utils.py               # LLM 初始化等工具
│   ├── tools.py               # RAG Tool（向量检索）
│   ├── services/
│   │   └── database.py        # SQLite 封装（reviewops.db）
│   ├── nodes/
│   │   ├── monitor.py         # 工单拉取（冷启动 / 增量 Batch_ID）
│   │   ├── filter.py          # 高危工单筛选
│   │   ├── rag.py             # RAG 归因
│   │   ├── agent.py           # 诊断路由（四类枚举）
│   │   └── action.py          # 行动生成 + 写 DB
│   └── ui/
│       ├── tab_dashboard.py   # 晨会大盘 + 智能巡检工作台
│       ├── tab_playground.py  # 单票实验室
│       └── state.py           # session_state 初始化
├── app.py                     # Streamlit 入口（三页导航）
├── injest.py                  # 知识库向量化（注意文件名拼写）
├── seed_db.py                 # 冷启动基线预热（真实 LLM）
├── clear_data.py              # 清空增量或全量工单
├── cold_start_tickets.csv     # 冷启动存量（10 条 CS-*）
├── incremental_tickets.csv    # 增量巡检（50 条 INC-*，Batch_ID 1~10）
├── saas_knowledge.txt         # RAG 知识库原文
├── reviewops.db               # SQLite（运行后生成）
├── chroma_db/                 # 向量库（运行 injest 后生成）
├── docs/
│   ├── PRD_CURRENT.md         # 当前实现版 PRD
│   └── DATA_CALIBER_AND_SOURCES.md  # 数据口径说明（实现对照）
└── tests/                     # pytest 单元测试
```

## ⚙️ 配置管理

配置集中在 `src/config.py`，支持环境变量覆盖：

### LLM

```bash
LLM_MODEL=qwen3.7-max-2026-05-17
LLM_TEMPERATURE=0
DASHSCOPE_API_KEY=your-key
```

### 向量库 / RAG

```bash
VECTOR_DB_PATH=./chroma_db
RAG_TOOL_TOP_K=1
RAG_SCORE_THRESHOLD=0.25
RAG_CHROMA_FETCH_K=24
```

### Monitor（工单数据源）

```bash
MONITOR_MIN_TICKETS=7
MONITOR_TICKETS_CSV_PATH=cold_start_tickets.csv
MONITOR_TICKETS_INCREMENTAL_CSV=incremental_tickets.csv
MONITOR_SEED_CSV=                    # 非空时 seed_db 强制使用该 CSV
```

## 🔧 技术栈

- **前端**：Streamlit
- **工作流**：LangGraph
- **RAG**：LangChain + ChromaDB + DashScope Embedding（text-embedding-v3）
- **LLM**：阿里千问（qwen3.7-max-2026-05-17，可通过 `LLM_MODEL` 覆盖）
- **存储**：SQLite（`reviewops.db`）
- **数据**：Pandas

## 📊 核心功能

### 1. 晨会数据大盘

- **数据概览**：全库工单数、AI 独立闭环率、估算节省工时、需研发介入单量
- **AI 技术简报**：基于 DB 真实数据 + LLM 生成（点击按钮触发）
- **工单工作台**：一线待办（待处理 / 已闭环）、研发疑难队列

> 指标口径详见 [docs/DATA_CALIBER_AND_SOURCES.md](docs/DATA_CALIBER_AND_SOURCES.md)。

### 2. 智能巡检工作台

- 点击「▶️ 运行全量智能工作流」触发 LangGraph
- 从 `incremental_tickets.csv` 按 `Batch_ID` 顺序拉取当前批次（不随机）
- 实时 Pipeline 日志 + 可恢复的「批次流水账」
- 分析结果写入 DB，在晨会大盘闭环处理

### 3. 单票实验室

- 输入单条客诉，Tool 调用归因
- 默认 Dry-run；勾选后可写入正式 `tickets` 表

### 4. 行动建议类型

- 🐞 **Jira Ticket**（产品缺陷）
- 📧 **Email Draft**（客服邮件 / SOP 闭环）
- ⬆️ **Escalate**（疑难转 L2 / 人工）
- 筛选节点可将低危工单标记为 **intercepted**（无需进入 RAG）

## 🏗️ 架构设计

### 工作流

```
monitor → filter → rag_analysis → agent_node
  → generate_email | generate_jira | escalate_human
  → next_route →（循环或 END）
```

### 数据流

| 阶段 | 数据源 | 说明 |
|------|--------|------|
| 冷启动 | `cold_start_tickets.csv` | App 空库自动 pending 入库；`seed_db.py` 全量分析 |
| 增量巡检 | `incremental_tickets.csv` | 按 `Batch_ID` 逐批，状态 `monitor_next_batch_id` 轮转 |
| 持久化 | `reviewops.db` | 分析结果、状态、指标统计、巡检游标与批次流水账 SSOT |

### 模块化职责

- `src/graph.py`：图构建与路由
- `src/nodes/`：各节点实现
- `src/services/database.py`：DB 与黄金指标分桶
- `src/ui/`：Streamlit 页面与 session 状态
- `app.py`：页面路由与侧边栏

## 📝 使用说明

### 典型演示流程

1. `cp .env.example .env` 并配置 API Key
2. `python injest.py` 构建向量库
3. `python seed_db.py` 预热冷启动基线（可选但推荐）
4. `streamlit run app.py`
5. 在「晨会数据大盘」查看指标与工单
6. 在「智能巡检工作台」多次运行工作流，模拟增量批次（Batch 1 → 2 → …）
7. 在「单票实验室」测试单条归因

### 重置数据

```bash
# 仅删除增量工单（保留 CS-* 基线）
python clear_data.py

# 清空全部后重新 seed
python clear_data.py --all
python seed_db.py
```

## 🧪 开发与测试

```bash
pytest tests/ -q
```

- **新增节点**：在 `src/nodes/` 添加模块，在 `src/graph.py` 注册
- **调整筛选**：`src/config.py` → `FilterConfig.KEYWORDS`
- **优化 RAG**：`src/config.py` → `VectorStoreConfig`，或调整 `injest.py` 切分策略
- **数据口径**：修改指标时同步更新 `docs/DATA_CALIBER_AND_SOURCES.md`

## 🔒 安全提示

提交代码前请确保：

1. 无硬编码 API Key
2. `.env` 不进入版本库
3. 敏感配置仅通过环境变量管理

## 📄 许可证

MIT License
