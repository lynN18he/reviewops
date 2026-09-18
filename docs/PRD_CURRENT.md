# ReviewOps 当前版本 PRD

文档版本：2026-09-08  
适用范围：当前代码实现版，作为后续演示、验收和迭代的产品依据。  
参考事实来源：`README.md`、`docs/DATA_CALIBER_AND_SOURCES.md`、`app.py`、`src/graph.py`、`src/ui/`、`src/nodes/`、`src/services/database.py`。

---

## 1. 产品概述

ReviewOps 是一个面向 B2B 电商履约与物流 SaaS 场景的研发智能问诊中台原型。系统以客诉工单为输入，通过 LangGraph 工作流、RAG 知识检索、LLM 诊断路由和行动建议生成，帮助支持、产品和研发团队完成工单分诊、归因、升级和闭环。

当前版本定位为可演示 MVP，而非生产级 SaaS。它重点展示以下能力：

- 将冷启动工单和增量工单写入本地 SQLite，形成统一事实源。
- 从知识库中检索 SOP、已知缺陷和发版信息，为工单归因提供证据。
- 自动判断工单是否需要进入高危分析流程。
- 将高危工单路由为配置问题、已知缺陷、新回归或未知升级。
- 自动生成客户邮件、研发 Jira 或人工升级建议。
- 在晨会看板中展示指标、AI 技术简报和待处理工单队列。
- 提供单票实验室，用于对单条客诉进行定向归因。

---

## 2. 产品目标

### 2.1 业务目标

- 降低 L1 / L2 支持团队排查重复问题的成本。
- 将已知 SOP、已知缺陷、发版影响与客户反馈自动关联。
- 让 PM 和研发在晨会上快速看到工单健康度、缺陷风险和需要介入的事项。
- 通过可演示的批次巡检流程，模拟“定时同步 / 按需拉取 / 智能分诊”的 ToB 运维场景。

### 2.2 当前版本成功标准

- 用户可以启动应用并看到三页导航：晨会数据大盘、智能巡检工作台、单票实验室。
- 空库时系统可以从 `cold_start_tickets.csv` 摄入冷启动工单。
- 用户可以通过 `seed_db.py` 预热基线数据，形成可展示的大盘指标。
- 用户可以点击运行智能工作流，从 `incremental_tickets.csv` 按 `Batch_ID` 拉取增量工单并完成分析。
- 分析结果写入 `reviewops.db`，并能在大盘和工单工作台中展示。
- 单票实验室可以输入一条客诉，调用 Tool + LLM 返回归因证据和行动建议。
- 核心单元测试通过，保障配置、图、节点和工具函数的基本行为稳定。

---

## 3. 用户角色

### 3.1 晨会参与者

典型用户：PM、研发负责人、支持主管。  
核心诉求：在每日晨会上快速掌握工单总体健康度、AI 闭环效果、研发介入压力和主要故障类型。

### 3.2 智能巡检操作者

典型用户：支持工程师、运维同学、Demo 演示者。  
核心诉求：手动触发一次智能巡检，观察系统如何同步工单、筛选高危、归因、路由和生成行动建议。

### 3.3 单票诊断用户

典型用户：产研、测试、L2 支持。  
核心诉求：针对一条具体客诉或日志进行定向归因，验证知识库和智能体判断是否合理。

---

## 4. 信息架构

当前版本采用 Streamlit 侧边栏导航，包含三个主页面：

| 页面 | 入口文案 | 当前职责 |
|------|----------|----------|
| 晨会数据大盘 | `📊 晨会数据大盘` | 展示指标、AI 技术简报、工单工作台 |
| 智能巡检工作台 | `⚡ 智能巡检工作台` | 触发 LangGraph 工作流，展示运行日志和批次流水账 |
| 单票实验室 | `🔬 单票实验室` | 对单条客诉进行 Tool 调用归因和行动建议生成 |

侧边栏同时展示：

- 当前产品：B2B 电商履约与物流 SaaS。
- API 配置状态：优先读取 `.env` / 环境变量中的 `DASHSCOPE_API_KEY`，否则允许用户输入。
- 数据源说明：`saas_knowledge.txt`、`cold_start_tickets.csv`、`incremental_tickets.csv`。

---

## 5. 核心功能需求

### 5.1 晨会数据大盘

#### 5.1.1 数据概览

系统应展示四个核心指标：

| 指标 | 当前实现口径 |
|------|--------------|
| 今日新增工单 | SQLite `tickets` 表全库累计条数，包含 `pending`；当前 Demo 用全库模拟单日流量 |
| AI 独立闭环率 | `resolved` 分桶 / 已处理工单数；包含筛选拦截和 Email Draft 闭环 |
| 约节省客服工时 | AI 独立闭环单量 × 0.25 小时 |
| 需研发介入单量 | `Escalate` 数量 + `Jira Ticket` 数量 |

说明：

- 后三项比例的分母是已处理工单，即 `status != 'pending'`。
- `pending` 工单计入总量，但不计入三率分母。
- “今日新增工单”当前不是自然日过滤，而是 Demo 口径下的全库累计。

#### 5.1.2 AI 技术简报

用户点击“基于真实大盘数据生成晨报”后，系统应：

- 读取近 24 小时内 `status IN ('analyzed', 'resolved')` 且 `is_test=0` 的工单作为叙事采样。
- 同时读取全库累计指标作为数字锚点。
- 调用 LLM 生成管理视角的晨会技术简报。
- 强制简报日期使用 Asia/Shanghai 当前日期。
- 当 24 小时采样为空但全库非空时，要求模型说明时间窗口差异，不得用 0 覆盖全库事实。

#### 5.1.3 工单工作台

系统应展示两个队列：

| 队列 | 展示内容 |
|------|----------|
| 一线待办 | `status='analyzed'` 且 action 为 `Jira Ticket` 或 `Email Draft` 的工单 |
| 研发疑难 | `status='analyzed'` 且 action 为 `Escalate` 的工单 |

一线待办中应支持将工单标记为已闭环，状态更新为 `resolved`。

---

### 5.2 智能巡检工作台

#### 5.2.1 工作流触发

用户点击“运行全量智能工作流”后，系统应启动 LangGraph 工作流：

```text
monitor → filter → rag_analysis → agent_node
  → generate_email_node | generate_jira_node | escalate_human_node
  → next_route → END
```

触发前置条件：

- 必须存在有效 DashScope API Key。
- SQLite 中持久化 `monitor_next_batch_id`，用于控制下一次增量批次读取；页面初始化时从 DB 恢复。

#### 5.2.2 数据同步

Monitor 节点应支持三种输入路径：

| 模式 | 行为 |
|------|------|
| SEED 模式 | 当 `MONITOR_SEED_CSV` 非空时，从指定 CSV 顺序读取，最多 500 条 |
| 增量模式 | 存在 `incremental_tickets.csv` 时，按当前 `Batch_ID` 读取整批工单 |
| 回退模式 | 无增量文件时，从 `cold_start_tickets.csv` 读取，受 `MONITOR_MIN_TICKETS` 限制 |

增量模式下：

- 系统读取 `incremental_tickets.csv` 中 `Batch_ID == monitor_next_batch_id` 的全部工单。
- 批次号每次运行后递增，超过最大批次后回到 1。
- 已存在且不需要再次分析的 `ticket_id` 会被跳过。
- 如果冷启动工单仍处于 `pending` 且没有 RAG 结果，应前置并入本批流水线，避免冷启动数据卡住。

#### 5.2.3 高危筛选

Filter 节点应根据 B2B SaaS 运维标准筛选 P0 / P1 高危工单。高危标准包括：

- 核心业务阻断，如无法登录、白屏、订单同步大面积停滞。
- 系统级报错，如 502、504、数据库超时、401 / 403 鉴权彻底失效。
- 客户情绪强烈且涉及资损、业务停摆或理赔。

当 LLM 调用失败时，系统应使用关键词降级策略。未进入高危分析的工单应被标记为 `intercepted`，形成状态闭环。

#### 5.2.4 RAG 归因

RAG 节点应对高危工单调用 Tool + ChromaDB 知识库进行归因。知识库来源包括：

- API / SOP 排查手册。
- 已知缺陷记录。
- 发版记录。

三个 RAG Tool 应按知识库 chunk metadata 中的 `doc_type` 约束检索范围：

- `search_known_issues` 只检索 `doc_type='jira_ticket'`。
- `search_release_notes` 只检索 `doc_type='release_note'`。
- `search_api_docs_and_sop` 只检索 `doc_type='SOP'`。

当 Agent 未调用任何 Tool 而触发系统兜底检索时，可以保留全库检索，以提高异常情况下的召回率。

RAG 结果应包含：

- `ticket_id`
- `ticket_content`
- `conclusion`
- `reason`
- `evidence`
- `knowledge_relevant`

当知识库无高匹配依据、模型网络失败、鉴权失败或额度不可用时，系统应返回面向业务用户的安全错误信息，不暴露底层 HTTP 细节。

#### 5.2.5 诊断路由

Agent 节点应将 RAG 结果路由到四类枚举：

| 路由 | 含义 | 后续动作 |
|------|------|----------|
| `USER_CONFIG_ERROR` | 用户配置、Token、授权或 SOP 类问题 | 生成客户邮件 |
| `KNOWN_ISSUE` | 已知缺陷且有 Jira 编号 | 生成客户邮件，说明已知问题和临时方案 |
| `NEW_REGRESSION` | 新 Bug 或发版回归 | 生成 P0 Jira |
| `UNKNOWN_ESCALATE` | 知识库无依据或无法判断 | 转 L2 人工 |

路由要求：

- 知识库不相关或拒答结果必须进入 `UNKNOWN_ESCALATE`。
- 只有证据明确指向 Jira 缺陷库且结论为已知缺陷时，才应判为 `KNOWN_ISSUE`。
- SOP 证据不得被错误归类为产品已知缺陷。

#### 5.2.6 行动建议

系统应根据路由生成行动建议并写入 DB：

| 动作 | 触发路由 | 产出 |
|------|----------|------|
| Email Draft | `USER_CONFIG_ERROR`、`KNOWN_ISSUE` | 客户解释邮件、SOP 引导或已知问题说明 |
| Jira Ticket | `NEW_REGRESSION` | P0 Jira 标题、描述、复现步骤 |
| Escalate | `UNKNOWN_ESCALATE` | L2 人工升级说明 |

写入 DB 时应更新：

- `rag_result`
- `action_plan`
- `risk_level`
- `urgency_level`
- `category`
- `status='analyzed'`
- `analyzed_at`

#### 5.2.7 运行日志与批次流水账

巡检页应在当前会话中展示：

- 工作流节点日志。
- 本次同步工单 ID。
- 本次 RAG 结果数量。
- 本次行动建议数量。
- 批次流水账，包括扫描数量、高危数量、扫描工单列表和高危摘要。

持久化要求：

- `monitor_next_batch_id`、`last_run_time` 和批次流水账应写入 SQLite。
- 页面刷新或重启后，巡检页应能从 DB 恢复上次运行时间、下一批次游标和历史批次。
- 运行中的实时日志仍可保存在 `st.session_state`，运行完成后的历史以 DB 为准。

---

### 5.3 单票实验室

用户应可以输入一条客诉或日志原文，点击“开始定向分析”后完成：

- API Key 校验。
- LLM 初始化。
- Tool 调用式 RAG 归因。
- 证据展示。
- 行动建议生成。

当前 UI 提供“将此测试数据写入正式大盘统计”的复选框，但当前代码路径中未完成正式写库动作。因此当前版本的单票实验室实际以 Dry-run 分析展示为主。

单票行动建议支持以下类型：

- `Jira Ticket`
- `Doc Update`
- `Email Draft`
- `Meeting`

说明：

- 单票实验室不经过完整 LangGraph 主流程。
- 单票行动类型集合与主流程动作集合并不完全一致。
- 单票实验室当前更适合用于归因调试、知识库验证和 Demo 展示。

---

## 6. 数据设计

### 6.1 输入数据

| 文件 | 作用 | 当前结构 |
|------|------|----------|
| `cold_start_tickets.csv` | 冷启动存量工单 | 10 条 `CS-*` 工单，`Batch_ID=0` |
| `incremental_tickets.csv` | 增量巡检工单 | 50 条 `INC-*` 工单，按 `Batch_ID` 分批 |
| `saas_knowledge.txt` | RAG 原始知识库 | SOP、缺陷、发版等知识文本 |
| `chroma_db/` | 向量库 | 由 `injest.py` 构建 |

CSV 核心列：

- `Ticket_ID`
- `Batch_ID`
- `User_Message`
- `True_Category`
- `Expected_Tool`
- `Expected_Ground_Truth_ID`

其中 `True_Category`、`Expected_Tool`、`Expected_Ground_Truth_ID` 同时服务于演示解释和离线评测。

### 6.2 SQLite 表

当前系统使用 `reviewops.db` 中的 `tickets` 表作为主要事实源。核心字段包括：

| 字段 | 含义 |
|------|------|
| `ticket_id` | 工单唯一 ID |
| `ticket_content` | 客诉或日志原文 |
| `source` | 数据来源，如 `seed_csv`、`incremental_tickets_csv`、`single_ticket` |
| `timestamp` | 工单时间 |
| `risk_level` | 风险等级 |
| `rag_result` | RAG 归因结果 JSON |
| `action_plan` | 行动建议 JSON |
| `created_at` | 入库时间 |
| `urgency_level` | P0 / P1 / P2 等紧急程度 |
| `category` | 业务分类，如技术支援、研发升级 |
| `status` | `pending`、`analyzed`、`intercepted`、`resolved` |
| `is_test` | 是否为测试数据 |
| `analyzed_at` | 完成分析时间 |

### 6.3 工作流运行状态表

当前系统使用轻量 SQLite 表保存巡检运行状态：

| 表 | 含义 |
|------|------|
| `workflow_meta` | 保存 `monitor_next_batch_id`、`last_run_time` 等键值型运行元数据 |
| `workflow_runs` | 保存每次巡检的批次流水账，包括批次时间、扫描数量、高危摘要、安全数量和扫描 ID |

### 6.4 状态定义

LangGraph 主流程使用 `TicketState` 在节点间传递状态，关键字段包括：

- `incr_tickets`
- `critical_tickets`
- `rag_analysis_results`
- `diagnosis_routes`
- `diagnosis_category`
- `processed_route_types`
- `action_plans`
- `logs`
- `processed_ids`
- `monitor_next_batch_id`

---

## 7. 指标口径

### 7.1 黄金三指标

系统采用互斥分桶计算三类结果：

| 分桶 | 判定条件 |
|------|----------|
| `jira` | `action_plan.action_type == "Jira Ticket"` |
| `escalate` | `action_plan.action_type == "Escalate"` |
| `resolved` | `status == "intercepted"` 或 `action_plan.action_type == "Email Draft"` |

计算口径：

- 分母：所有 `status != 'pending'` 的工单。
- AI 独立闭环率：`resolved / processed`。
- 疑难升级率：`escalate / processed`。
- 缺陷识别率：`jira / processed`。

### 7.2 24 小时简报口径

AI 技术简报使用两个口径：

- 叙事采样：近 24 小时内 `status IN ('analyzed', 'resolved')` 且 `is_test=0` 的工单。
- 数字锚点：全库累计指标与黄金分桶。

产品上应明确展示“近 24 小时采样”和“全库累计”是两个不同口径。

---

## 8. 配置与环境

当前版本支持通过环境变量配置：

| 配置 | 默认值 | 用途 |
|------|--------|------|
| `DASHSCOPE_API_KEY` | 无 | DashScope LLM / Embedding 鉴权 |
| `LLM_MODEL` | `qwen3.7-max-2026-05-17` | LLM 模型 |
| `LLM_TEMPERATURE` | `0` | 模型温度 |
| `VECTOR_DB_PATH` | `./chroma_db` | 向量库目录 |
| `RAG_TOOL_TOP_K` | `1` | Tool 检索返回文档数，上限限制为 2 |
| `RAG_SCORE_THRESHOLD` | `0.25` | similarity score threshold 检索阈值 |
| `RAG_CHROMA_FETCH_K` | `24` | Chroma 候选池大小 |
| `MONITOR_MIN_TICKETS` | `7` | 非增量回退模式批量数量 |
| `MONITOR_TICKETS_CSV_PATH` | `cold_start_tickets.csv` | 冷启动 CSV |
| `MONITOR_TICKETS_INCREMENTAL_CSV` | `incremental_tickets.csv` | 增量 CSV |
| `MONITOR_SEED_CSV` | 空 | `seed_db.py` 强制 seed 数据源 |

相对路径应通过仓库根目录解析，避免从不同 cwd 启动时找不到 CSV 或向量库。

---

## 9. RAG 质量评测

当前版本暂不交付独立的离线 RAG 评测脚本。RAG 行为主要通过单元测试、人工验收和演示样本验证。

后续如需将 RAG 质量纳入正式验收，应补充：

- 覆盖 SOP、Jira、发版、超纲、噪音样本的标注集。
- 检索命中率、工具调用准确率和拒答准确率等硬指标。
- 可复现的评测命令、逐条失败原因和调优记录。

---

## 10. 非功能需求

### 10.1 可演示性

- 支持本地一键启动：`streamlit run app.py`。
- 支持冷启动基线预热：`python seed_db.py`。
- 支持多次点击巡检按钮模拟增量批次同步。
- UI 应清楚展示运行日志、批次结果和工单闭环入口。

### 10.2 稳定性与降级

- LLM 筛选失败时应使用关键词降级筛选。
- RAG / LLM 失败时应返回业务可理解的错误信息。
- 不应把底层网络、HTTP、SDK 细节直接暴露给业务用户。
- 未检索到高匹配知识时，应转人工，不应强行生成确定性结论。

### 10.3 安全与配置

- API Key 不应硬编码。
- `.env` 不应提交到版本库。
- 侧边栏可以输入 API Key，但推荐使用环境变量。
- 输出给客户的邮件和行动建议应遵守防幻觉约束，不能编造知识库没有提供的具体时间、参数或示例。

### 10.4 可测试性

- 配置、图构建、节点逻辑、工具函数应有单元测试覆盖。
- 当前测试入口为 `pytest tests/ -q`。
- 修改指标、数据口径、RAG 行为或路由枚举时，应同步更新测试和 `docs/DATA_CALIBER_AND_SOURCES.md`。

---

## 11. 当前限制

当前版本存在以下已知限制：

- “今日新增工单”当前实现为全库累计条数，不是真实自然日新增。
- 单票实验室的“写入正式大盘统计”复选框当前尚未真正完成写库流程。
- 单票实验室不经过完整 LangGraph，因此和主流程在路由、动作类型和状态写入上存在差异。
- 早期产品设计文档已被当前实现版 PRD 取代，后续需求口径应以本文档为准。
- 当前尚未建立完整的离线 RAG 评测体系，不能仅凭演示样本证明 RAG 质量已达标。
- 当前系统使用本地 SQLite、CSV 和本地 ChromaDB，尚未接入真实 Jira、Notion、CRM、客服系统或生产数据库。

---

## 12. 后续迭代建议

### 12.1 P0：补齐当前演示闭环

- 完成单票实验室写入正式大盘的 DB 逻辑。
- 明确“今日新增”是否继续使用 Demo 全库口径，或改为真实自然日过滤。
- 校准 `README.md`、`docs/DATA_CALIBER_AND_SOURCES.md` 和本 PRD 的批次数、数据量描述。

### 12.2 P1：增强 RAG 质量与可解释性

- 扩充评测集，覆盖 SOP、Jira、发版、超纲、噪音等类型。
- 建立可复现的离线评测脚本，输出逐条样本结果和失败原因。
- 为每次归因展示命中的知识源 ID、证据片段和工具调用路径。
- 将 RAG 质量指标纳入回归测试或手动验收清单。

### 12.3 P2：生产化方向

- 接入真实工单系统、Jira、知识库和用户权限体系。
- 将本地 SQLite 替换为生产数据库。
- 支持多租户、审计日志和操作追踪。
- 将工作流运行、节点耗时、失败原因和模型调用成本持久化。
- 增加人工反馈回流，用于持续优化知识库、路由规则和行动模板。

---

## 13. 验收清单

当前版本可按以下步骤验收：

1. 配置 `.env` 中的 `DASHSCOPE_API_KEY`。
2. 执行 `python injest.py` 构建向量库。
3. 执行 `python seed_db.py` 生成冷启动基线。
4. 执行 `streamlit run app.py` 启动应用。
5. 在晨会数据大盘确认指标、简报按钮和工单工作台可见。
6. 在智能巡检工作台点击运行工作流，确认能按增量批次同步并写入 DB。
7. 回到晨会数据大盘，确认新增分析结果进入对应队列。
8. 在单票实验室输入客诉，确认能返回归因证据和行动建议。
9. 执行 `pytest tests/ -q`，确认测试通过。

