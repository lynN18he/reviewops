# ReviewOps 交接说明

本文档用于快速交接当前项目现状。完整产品口径请看 `docs/PRD_CURRENT.md`，数据口径请看 `docs/DATA_CALIBER_AND_SOURCES.md`。

## 1. 项目定位

ReviewOps 是一个面向 B2B 电商履约 / 物流 SaaS 场景的 AI 工单分诊 Demo。它模拟客服、产品、研发在处理客户异常工单时的协作流程：

- 从冷启动 CSV 或增量 CSV 读取客户工单。
- 用 LangGraph 串起 Monitor、Filter、RAG、Agent、Action 节点。
- 用 ChromaDB + DashScope Embedding 检索 SOP、已知缺陷和发版记录。
- 用千问 LLM 进行高危筛选、归因、诊断路由和行动建议生成。
- 在 Streamlit 大盘中展示指标、晨会简报、待办队列和巡检流水账。

当前项目是可演示 MVP，不是生产级系统。

## 2. 当前主要能力

- 晨会数据大盘：展示累计工单数、AI 闭环率、节省工时估算和研发介入量。
- AI 技术简报：基于 SQLite 中的真实工单结果生成晨会摘要。
- 智能巡检工作台：按 `incremental_tickets.csv` 的 `Batch_ID` 逐批处理增量工单。
- RAG 归因：三个 Tool 分别按 `doc_type` 检索 SOP、Jira 缺陷和发版记录。
- 行动建议：根据路由生成客户邮件、P0 Jira 或人工升级建议。
- 单票实验室：支持单条客诉 Dry-run 归因，用于展示和调试。
- SQLite 持久化：保存工单、分析结果、巡检游标、上次运行时间和批次流水账。

## 3. 运行方式

首次运行：

```bash
cd /Users/lynnhe/Desktop/reviewops
pip install -r requirements.txt
cp .env.example .env
```

在 `.env` 中填入 `DASHSCOPE_API_KEY` 后，构建知识库：

```bash
python injest.py
```

启动应用：

```bash
streamlit run app.py
```

如果希望大盘启动后已有分析基线，可先运行：

```bash
python seed_db.py
streamlit run app.py
```

如果希望从零开始体验：

```bash
rm -f reviewops.db
python injest.py
streamlit run app.py
```

## 4. 关键文件

- `app.py`：Streamlit 入口。
- `src/graph.py`：LangGraph 工作流组装。
- `src/nodes/`：Monitor、Filter、RAG、Agent、Action 节点。
- `src/tools.py`：RAG Tool 和 Chroma 检索逻辑。
- `src/services/database.py`：SQLite 读写、指标计算、workflow 状态持久化。
- `src/ui/`：Streamlit 页面和 session 初始化。
- `injest.py`：把 `saas_knowledge.txt` 切分、向量化并写入 `chroma_db/`。
- `seed_db.py`：对冷启动工单跑完整工作流，生成大盘基线。
- `cold_start_tickets.csv`：冷启动演示工单。
- `incremental_tickets.csv`：增量巡检演示工单。
- `saas_knowledge.txt`：RAG 知识库原文。

## 5. 交接注意事项

- `.env` 不应提交或转发，交接时使用 `.env.example`。
- `reviewops.db` 是本地运行生成的数据文件，不建议作为源码交接。
- `chroma_db/` 是运行 `python injest.py` 生成的向量库，不建议提交到 Git。
- `.langgraph_api/` 是 `langgraph dev` 的运行时缓存，不需要交接。
- `langgraph.json` 可保留，后续若用 LangGraph Studio 调试会用到。
- `GRAPH_EXPLAINED.md` 是工作流入门说明，适合同事快速理解节点流转。

## 6. 当前已知局限

- “今日新增工单”当前是 Demo 口径，实际展示的是全库累计工单数，不是真实自然日新增。
- 单票实验室的“写入正式大盘统计”尚未形成完整 DB 闭环，目前更适合 Dry-run 展示。
- 单票实验室和主流程的行动类型不完全一致，长期需要统一。
- Jira、Notion、邮件等外部系统动作仍是模拟按钮，没有真实 API 集成。
- RAG 质量目前主要靠样本、单元测试和人工验收，没有完整离线评测体系。
- 当前系统使用本地 CSV、SQLite 和 ChromaDB，尚未接入真实工单系统、知识库、权限和审计。

## 7. 作为 AI PM 面试 Demo 的亮点

- 场景完整：从工单输入、风险筛选、知识归因、路由决策到行动建议，覆盖支持到研发的协作链路。
- AI PM 叙事清晰：能展示如何把 AI 能力落到具体业务指标，例如闭环率、节省工时和研发介入量。
- 架构可解释：LangGraph 节点化流程便于讲清楚每一步为什么存在，以及如何避免黑盒决策。
- RAG 有真实约束：Tool 检索按 `doc_type` 分工，减少“工具名和检索范围不一致”的问题。
- Demo 可操作：Streamlit 大盘、批次巡检、单票实验室都可以现场演示。

## 8. 面试展示时的风险

- 如果面试官追问生产化，当前 Demo 还缺真实系统集成、权限、安全审计、监控告警和成本治理。
- 如果追问 RAG 质量，当前还不能用大规模评测数据证明准确率，只能说明已有小样本和测试保护。
- 如果追问指标口径，“今日新增”需要主动说明是 Demo 口径，避免被认为指标造假。
- 如果追问闭环动作，当前 Jira / 邮件 / Notion 按钮偏模拟，需要说明这是产品原型阶段。
- 如果现场网络或 DashScope API 不稳定，`injest.py`、`seed_db.py` 或工作流 LLM 调用可能失败，建议提前预热并保留可展示的本地 DB。

## 9. 建议后续改进

优先级较高：

- 修正“今日新增工单”口径，或将文案改为“累计接单”。
- 补齐单票实验室写入 DB 的正式流程，或移除“写入正式大盘统计”的 checkbox。
- 统一单票实验室和主流程的路由、行动类型与状态写入。
- 建立最小可复现 RAG 评测集，输出命中率、工具调用准确率、拒答准确率和失败案例。

中长期方向：

- 接入真实 Jira、客服系统、知识库和邮件系统。
- 增加用户权限、审计日志、操作追踪和错误告警。
- 记录每次工作流的节点耗时、模型调用失败原因和成本。
- 将本地 SQLite 替换为生产数据库，并补正式 migration 机制。
- 为 PM 面试准备一条固定演示路径，包括初始大盘、一次增量巡检、一个单票归因和一个行动闭环故事。
