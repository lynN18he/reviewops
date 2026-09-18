# ReviewOps 数据口径与来源梳理

本文档按模块梳理当前系统中**每一部分的数据口径和来源**，便于排查不一致和后续改造。

> 文件名约定（2026-04 起）：`cold_start_tickets.csv`（冷启动存量）、`incremental_tickets.csv`（增量巡检）。早期测试 CSV 命名已废弃。

---

## 一、数据源总览

| 数据源 | 说明 | 使用处 |
|--------|------|--------|
| **SQLite `tickets` 表**（`reviewops.db`） | 持久化工单 + `rag_result` / `action_plan` / `status` / `analyzed_at` | 看板指标、工单工作台、简报采样、monitor 去重 |
| **SQLite `workflow_meta` / `workflow_runs`** | 持久化巡检游标、上次运行时间、批次流水账 | App 初始化恢复状态、巡检页展示历史批次 |
| **cold_start_tickets.csv** | 冷启动存量（10 条 CS-*，含评测标注列） | App 空库自动摄入；`seed_db.py` 全量分析基线；monitor 主路径 |
| **incremental_tickets.csv** | 增量巡检（50 条 INC-*，按 `Batch_ID` 1~10 分批） | monitor 节点：每次「运行智能工作流」拉取当前批次 |
| **saas_knowledge.txt** + **chroma_db/** | RAG 知识库与向量索引；chunk metadata 含 `doc_type` | `injest.py` 构建；RAG Tool 按 `doc_type` 检索 |
| **st.session_state** | 会话内 UI 缓存（`all_tickets`、本轮临时 RAG 结果等） | 页面渲染与运行中日志；关键巡检状态从 DB 恢复 |

---

## 二、各模块数据口径与来源

### 1. 晨会数据大盘 — 顶部「数据概览」四张指标卡

实现位置：`src/ui/tab_dashboard.py` → `render_dashboard_metrics()` → `app.calculate_metrics()` → `db.get_dashboard_metrics()`。

| 指标（UI 文案） | 口径（当前实现） | 数据来源 |
|----------------|------------------|----------|
| **📥 今日新增工单** | `tickets` 表 **全表** `COUNT(*)`（含 `pending`）；**无**「今日」时间过滤，Demo 以全库条数模拟单日流量 | `get_dashboard_metrics()[0]` |
| **🤖 AI 独立闭环率** | 分子：`resolved` 分桶条数；分母：`status != 'pending'` 的已处理条数；保留 1 位小数 | `get_dashboard_metrics()[1]`、`[5]` |
| **⏱️ 约节省客服工时** | `resolved_count × 0.25`（假设每单人工 15 分钟） | 由 `[5]` 推导，非 DB 字段 |
| **🚨 需研发介入单量** | `escalated_count + jira_count`（疑难转 L2 + 已知缺陷 Jira） | `get_dashboard_metrics()[6]`、`[7]` |

**黄金三指标互斥分桶**（`database._golden_ticket_bucket()`，优先级从高到低）：

| 分桶 | 判定条件 |
|------|----------|
| **jira** | `action_plan.action_type == "Jira Ticket"` |
| **escalate** | `action_plan.action_type == "Escalate"` |
| **resolved** | `status == "intercepted"` **或** `action_type == "Email Draft"` |
| **None** | 以上均不满足（不计入三率分子，但若 `status != pending` 仍计入分母） |

**三率分母**：仅 `status != 'pending'`（且非空）的工单；`pending` 积压**不计入**三率分母，但**计入**「今日新增工单」总数。

**注意**：第一张卡片文案为「今日新增工单」，实现为**全库累计**，无 `created_at` 当日过滤；help 文案已说明 Demo 口径。

---

### 2. AI 技术简报

实现位置：`tab_dashboard._generate_daily_briefing()`（按钮「基于真实大盘数据生成晨报」触发）。

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **简报日期** | 上海时区当日 | `_briefing_today_zh()` |
| **24h 采样列表** | 近 24h 内 `status IN ('analyzed','resolved')` 且 `is_test=0` 的工单，最多 100 条 | `db.get_briefing_tickets_24h()` |
| **全库指标锚点** | 与顶部四张卡同源：`get_dashboard_metrics()` + `get_briefing_library_breakdown()` | 写入 LLM prompt  preamble，约束数字一致 |
| **正文四节** | LLM 动态生成（非固定模板） | 千问 LLM，基于采样 + 全库分解 |

简报**会**引用 DB 的 `rag_result` / `action_plan` 做叙事采样；全库比例须与大盘一致，24h 窗口与全库累计在 preamble 中显式区分。

---

### 3. 晨会数据大盘 — 工单工作台

| Tab | 口径 | 数据来源 |
|-----|------|----------|
| **一线待办 · 待处理** | `status='analyzed'` 且 `is_test=0`，且 `action_type IN ('Jira Ticket','Email Draft')` | `db.get_pending_tickets()` |
| **一线待办 · 已闭环** | `status='resolved'` 且 `is_test=0` | `db.get_resolved_tickets()` |
| **研发疑难** | `status='analyzed'` 且 `action_type='Escalate'` | `db.get_escalate_queue_tickets()` |

---

### 4. `all_tickets`（session_state）

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **用途** | 会话内工单列表缓存；**看板指标不读此列表**，只查 DB | `init_session_state()` |
| **初始化** | DB 非空 → 映射 `get_all_tickets()`；DB 为空 → `cold_start_ingest_tickets()` 读 `cold_start_tickets.csv` 写入 pending，再读 DB | `src/ui/state.py` |
| **回退** | 若 DB 与冷启动 CSV 均空 → `app.load_tickets()` 返回空表 | `cold_start_tickets.csv` |
| **后续更新** | 每次巡检 monitor 产出 `incr_tickets` 后 `extend` | `tab_dashboard.render_tab()` |

---

### 5. 智能工作流输入：`incr_tickets`（monitor 节点）

实现位置：`src/nodes/monitor.py`。

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **增量模式** | 存在 `incremental_tickets.csv` 时，按 `state.monitor_next_batch_id` 读取**整批** `Batch_ID` 工单（**不随机**）；批次号每次运行 +1，超过最大 Batch_ID 后回到 1 | `load_incremental_batch()` |
| **冷启动补跑** | 增量模式下，若冷启动 CSV 中有已在库且 `status=pending`、无 RAG 结论的 CS-*，前置并入本批 | `_pending_cold_incr_tickets()` |
| **SEED 模式** | 环境变量 `MONITOR_SEED_CSV` 非空（如 `seed_db.py` 设 `cold_start_tickets.csv`）时，从该 CSV 顺序读取，最多 500 条 | `MonitorConfig.SEED_CSV` |
| **非增量回退** | 无增量文件时，从 `MONITOR_TICKETS_CSV_PATH`（默认 `cold_start_tickets.csv`）读取，至多 `MIN_TICKETS_PER_BATCH` 条 | `MonitorConfig` |
| **去重** | `ticket_id` 已在 DB 且非「待再次分析」则跳过；否则 `db.add_ticket(..., status='pending')` | `db.exists()` / `is_pending_needs_analysis()` |
| **写入 DB 时机** | monitor 入库时**尚无** `rag_result` / `action_plan` | monitor 节点 |

默认配置（`src/config.py`）：

```bash
MONITOR_MIN_TICKETS=7
MONITOR_TICKETS_CSV_PATH=cold_start_tickets.csv
MONITOR_TICKETS_INCREMENTAL_CSV=incremental_tickets.csv
```

---

### 6. 工作流结果写入 DB

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **谁写入** | action 节点（`generate_email_node` / `generate_jira_node` / `escalate_human_node`）调用 `_update_db_for_plans()` | `src/nodes/action.py` |
| **写入内容** | `rag_result`、`action_plan`、`category`、`status`（如 `analyzed` / `intercepted`）、`analyzed_at` | `db.update_analysis()` |
| **RAG 节点** | 只产出 `rag_analysis_results` 进入 state，**不写 DB** | `src/nodes/rag.py` |

---

### 7. 智能巡检工作台 — 批次流水账

实现位置：`tab_dashboard.render_tab()` → `run_history`（session 缓存 + DB 持久化）。

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **触发** | 点击「▶️ 运行全量智能工作流」 | LangGraph `graph_app.stream()` |
| **单条 batch_record** | `{ batch_id, total_count, high_risk_tickets, safe_count, scanned_ids }` | 工作流 `final_state` + 高危摘要规则 |
| **batch_id** | 本次运行开始时间 `YYYY-MM-DD HH:MM:SS` | 非 CSV 的 `Batch_ID` |
| **高危摘要** | RAG 结果中 `action_type IN ('Jira Ticket','Email Draft')` 的条目 | 前端规则拼接，非 DB 查询 |
| **持久性** | 写入 SQLite，可在刷新/重启后恢复 | `workflow_runs` |

巡检页运行中仍使用当前会话展示实时日志；运行成功后，批次流水账写入 DB。长期结果同步至 DB 后，在「晨会数据大盘 → 工单工作台」查看与闭环。

---

### 8. 单票实验室

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **分析路径** | 独立 Tool 调用（`match_with_spec`），**不经过**完整 LangGraph | `tab_playground.py` |
| **Dry-run** | 默认勾选「不写入大盘」：仅前端展示 | 无 DB 写入 |
| **写入正式库** | 勾选后写入 `tickets`（`is_test=0`，`source=single_ticket`） | 可选 DB 写入 |

---

### 9. 侧边栏「数据源」

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| 文案 | 静态说明 | `app.py` 侧边栏：知识库 / 冷启动 / 增量 CSV 文件名 |
| API Key | 优先 `.env` 的 `DASHSCOPE_API_KEY`，否则侧边栏输入 | 环境变量或 `st.text_input` |

---

## 三、数据流简图

```
启动 App:
  init_session_state()
    → DB 空? cold_start_ingest_tickets(cold_start_tickets.csv) → pending 入库
    → all_tickets = DB 映射
    → monitor_next_batch_id / last_run_time / run_history = DB 恢复
  load_tickets() → cold_start_tickets.csv（侧边栏预览）

渲染「晨会数据大盘」:
  calculate_metrics() → db.get_dashboard_metrics()  → 四张指标卡
  点击生成晨报 → _generate_daily_briefing() → LLM + DB 采样

点击「运行全量智能工作流」（智能巡检工作台）:
  monitor:
    incremental_tickets.csv[Batch_ID=N] + 冷启动 pending 补跑
    → db.add_ticket(pending) → incr_tickets
    → monitor_next_batch_id += 1
  filter → critical_tickets
  rag_analysis → rag_analysis_results（不写 DB）
  agent_node → diagnosis_routes
  action 节点 → action_plans + _update_db_for_plans() → DB
  run_history.insert(0, batch_record) + save_workflow_run(batch_record)
  monitor_next_batch_id / last_run_time → workflow_meta
  all_tickets.extend(incr_tickets)

黄金基线预热（可选，推荐首次）:
  python injest.py
  MONITOR_SEED_CSV=cold_start_tickets.csv python seed_db.py
    → 清空 tickets → 跑完整图 → CS-* 写入 analyzed + rag/action
```

---

## 四、口径不一致与注意点汇总

1. **「今日」名实不符**：「今日新增工单」= 全库 `COUNT(*)`，非当日 `created_at` 过滤。
2. **三率分母 vs 总数**：总数含 `pending`；三率分母仅已处理（`status != pending`）。
3. **CSV Batch_ID vs 运行 batch_id**：增量 CSV 的 `Batch_ID` 控制 monitor 拉取批次；UI `run_history.batch_id` 是运行时间戳，二者不同。
4. **实时日志 vs 历史流水账**：运行中的日志仍在会话内展示；运行完成后的流水账持久化在 DB。
5. **空库自动摄入 vs seed_db**：App 启动仅把冷启动 CSV **入库为 pending**；完整 LLM 分析需手动跑巡检或 `seed_db.py`。
6. **单票实验室 vs 主流程**：实验室走简化 Tool 路径，与 LangGraph 全链路行为可能不一致。

---

## 五、相关脚本

| 脚本 | 作用 |
|------|------|
| `python injest.py` | 构建 / 重建 `chroma_db` 向量库 |
| `python seed_db.py` | 清空 DB，对 `cold_start_tickets.csv` 跑完整工作流，写入分析基线 |
| `python clear_data.py` | 默认仅删增量单（INC-*）；`--all` 清空全部 |

---

*文档版本：与当前代码对齐（2026-06）；逻辑变更时请同步更新。*
