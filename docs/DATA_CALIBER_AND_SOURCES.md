# ReviewOps 数据口径与来源梳理

本文档按模块梳理当前系统中**每一部分的数据口径和来源**，便于排查不一致和后续改造。

---

## 一、数据源总览

| 数据源 | 说明 | 使用处 |
|--------|------|--------|
| **SQLite `tickets` 表** | 持久化存储：工单基础信息 + `rag_result` / `action_plan`（分析结果） | 看板指标、简报 total、all_tickets 初始化、历史记录、指标计算 |
| **test_tickets.csv** | 存量工单 CSV，启动时由 `load_tickets()` 读取 | 仅用于 `tickets_df` → 当 DB 为空时初始化 `all_tickets` |
| **test_tickets_incremental.csv** | 增量工单 CSV | 工作流 monitor 节点：每次巡检从此文件读取并入库 |
| **st.session_state** | 会话状态（all_tickets、incident_history、last_run_increment 等） | 看板渲染、Hero、历史去重、delta 展示 |

---

## 二、各模块数据口径与来源

### 1. 顶部「数据概览」三个指标卡

| 指标 | 口径（当前实现） | 数据来源 |
|------|------------------|----------|
| **今日工单总数** | `tickets` 表 **全表** `COUNT(*)`，**无**“今日”时间过滤 | `calculate_metrics()` → `db.get_dashboard_metrics()` → `SELECT COUNT(*) FROM tickets` |
| **L1 智能拦截率** | 分子：被判定为「未转研发」的工单数；分母：同上全表总数；率 = 分子/分母×100%，保留 1 位小数 | 同上；分子由每条记录的 `action_plan`(JSON) 的 `action_type` 及 `category` 判定（见下） |
| **P0 研发升级率** | 分子：被判定为「转研发」的工单数；分母：全表总数；率 = 分子/分母×100% | 同上 |

**拦截/升级判定规则**（`get_dashboard_metrics()` 内）：

- **算作升级（escalated_count）**：`action_type == "Jira Ticket"` 或 `category == "研发升级"`。
- **算作拦截（deflected_count）**：`action_type in ("Email Draft", "Escalate")` 或 `category == "技术支援"`，或有其他非 Jira 的 `action_type`。
- **未写入 `action_plan` 的工单**：既不记入拦截也不记入升级，只计入分母（total_tickets）。

**注意**：指标名称是「今日工单总数」，但实现是**全表统计**，无日期过滤。

---

### 2. 指标卡下方的「本次新增 X 条工单」（delta_total）

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| 本次新增条数 | 当前会话**最近一次**点击「运行智能工作流」时，本批新入库的工单条数 | `st.session_state.last_run_increment` |
| 写入时机 | 工作流 stream 中检测到 `node_monitor` 的 `incr_tickets` 后：`last_run_increment = len(new_tickets)` |

---

### 3. AI 技术简报

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **「今日共处理 X 条工单」中的 X** | 与看板「今日工单总数」一致 | `generate_ai_brief(..., total_tickets)`，`total_tickets` 来自 `calculate_metrics()` → `get_dashboard_metrics()` 的 total |
| **其余正文**（整体系统健康度、核心故障发现、拦截成效、研发关注建议） | **固定模板**，无动态数据 | `app.py` 中 `generate_ai_brief()` 的硬编码字符串，仅 `{total}` 被替换 |

简报**未**从 DB 的 `rag_result` / `action_plan` / `diagnosis_category` 聚合生成。

---

### 4. `all_tickets`（session_state）

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **用途** | 供「数据概览」区构造 `all_tickets_df`，仅用于传入 `calculate_metrics(all_tickets_df, ...)`；**calculate_metrics 内部忽略 df，只查 DB**，故 all_tickets 仅影响「是否构造空 DataFrame」 | `init_session_state()` 中**仅首次**初始化 |
| **初始化逻辑** | 若 `db.get_all_tickets()` 非空 → `all_tickets` = DB 全量工单（映射为 ticket_id, user_id, timestamp, ticket_content, urgency_level, category）；否则 → `all_tickets` = **test_tickets.csv** 的 `tickets_df.to_dict('records')` | DB 优先；DB 空则用 CSV |
| **后续更新** | 每次运行工作流后，`node_monitor` 产出的 `incr_tickets` 会 **extend** 到 `all_tickets` | `tab_dashboard.py` 中 `st.session_state.all_tickets.extend(new_tickets)` |

因此：**看板三个指标不读 all_tickets**，只读 DB；all_tickets 主要用于「是否有数据建 DataFrame」以及列表展示（若有）。

---

### 5. 智能工作流输入：`incr_tickets`

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **每批条数** | 至少 `MIN_TICKETS_PER_BATCH` 条（默认 **2**），从当次读取的 CSV 中取「未入库且未在 processed_ids」的工单直到凑满 | `MonitorConfig.MIN_TICKETS_PER_BATCH`（环境变量 `MONITOR_MIN_TICKETS`） |
| **CSV 来源** | 若存在 **test_tickets_incremental.csv** 则只从该文件读；否则从 **test_tickets.csv** 读 | `load_tickets_from_csv(csv_path, max_count=100)`，`csv_path` 由 monitor 节点按配置与文件存在性决定 |
| **去重** | `ticket_id` 已在 DB 中存在（`db.exists(tid)`）或在当前 state 的 `processed_ids` 中则跳过 | monitor 节点内 |
| **写入 DB** | 本批每条工单立即 `db.add_ticket(...)`，此时**尚无** `rag_result` / `action_plan` | monitor 节点 |

---

### 6. 工作流结果写入 DB（rag_result / action_plan）

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **谁写入** | **仅 action 节点**（generate_email_node、generate_jira_node、escalate_human_node）在生成行动建议时调用 `_update_db_for_plans()` | `src/nodes/action.py` |
| **写入内容** | 对每条被该节点处理的工单：`db.update_analysis(ticket_id, rag_result=..., action_plan=..., category=...)` | 同一批次内的 `rag_analysis_results` + 本节点产出的 `action_plan` |
| **RAG 节点** | 只产出 `rag_analysis_results` 进入 state，**不写 DB**；写 DB 的 rag_result 来自 action 节点里带上的 RAG 结果 | `src/nodes/rag.py` 不调用 DB |

因此：**只有走过完整链路并进入某一 action 节点的工单**，才会在 DB 中有 `rag_result` 和 `action_plan`；仅入库但未进入 action 的工单，这两列为空。

---

### 7. Hero 区「本次巡检发现 (Latest)」

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **展示内容** | **最近一次**点击「运行智能工作流」产生的本批 RAG 结果 + 行动建议，按 ticket 成对展示 | `st.session_state.incident_history[0]` |
| **单条记录结构** | `batch_record = { 'time', 'rag_results', 'actions', 'new_tickets_count', 'critical_count' }` | 工作流结束后用 `final_state` 的 `rag_analysis_results`、`action_plans`、`incr_tickets` 等拼出，并 `insert(0)` 进 `incident_history` |
| **时间 / 新增条数** | `latest_time`、`latest_new_tickets` 来自该 batch 的 `time` 和 `new_tickets_count` | 同上 |

Hero **不读 DB**，只读 session 中**当次运行**写进的 `incident_history` 首项。

---

### 8. 「历史巡检记录」列表

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| **原始数据** | DB 中**最近 50 条**工单（按 `created_at DESC`），且每条必须有 `rag_result` 和 `action_plan` 非空 | `db.get_history(limit=50)` → `SELECT ... FROM tickets ORDER BY created_at DESC LIMIT 50` |
| **去重** | 若 Hero 区有展示本批（incident_history[0]），则从历史列表中**排除**该批中出现的 `ticket_id`，避免与 Hero 重复 | `filtered_history` = 去掉 `hero_ticket_ids` 且 `rag_result`、`action_plan` 非空的记录 |
| **展示分组** | 按工单的 `created_at` 的**日期**（YYYY-MM-DD）分组，同一天多条工单放在同一 expander 下 | 前端对 `filtered_history` 按 `created_at` 分组 |

注意：**历史是按「工单」维度**（每条 DB 记录一条工单），不是按「巡检批次」维度；同一次巡检的多条工单会按各自 `created_at` 落在不同日期下。

---

### 9. 侧边栏「数据源」与「最后更新」

| 项目 | 口径 | 数据来源 |
|------|------|----------|
| 工单数据 / 知识库 / 向量库 | 静态说明文案 | 写死为 `test_tickets.csv`、`saas_knowledge.txt`、`./chroma_db` |
| 最后更新 | **当前系统日期** | `datetime.now().strftime('%Y-%m-%d')`，非 DB 或 CSV 的最近更新时间 |

---

## 三、数据流简图

```
启动时:
  load_tickets() → test_tickets.csv → tickets_df
  init_session_state: all_tickets = db.get_all_tickets() 或 tickets_df（DB 空时）

每次渲染「数据概览」:
  all_tickets → all_tickets_df（仅用于传参，可空）
  calculate_metrics(all_tickets_df, ...) → 仅内部调用 db.get_dashboard_metrics()
    → 今日工单总数 / L1 拦截率 / P0 升级率（全表，无时间过滤）
  generate_ai_brief(all_tickets_df, total_tickets) → total 来自 DB，其余为固定模板

点击「运行智能工作流」:
  monitor: test_tickets_incremental.csv（或 test_tickets.csv）→ 随机打乱 → 取未入库的至少 MIN 条
    → db.add_ticket(...) → incr_tickets 产出
  filter → critical_tickets
  rag_analysis → rag_analysis_results（不写 DB）
  agent_node → diagnosis_routes / diagnosis_category
  action 节点 → action_plans，并 _update_db_for_plans() 写 DB（rag_result + action_plan）
  结束后：incident_history.insert(0, batch_record)，all_tickets.extend(new_tickets)，last_run_increment = len(new_tickets)
```

---

## 四、口径不一致与注意点汇总

1. **「今日」名实不符**：指标名为「今日工单总数」，实际为 tickets 表全表 COUNT，无今日过滤。
2. **简报与看板**：仅「今日共处理 X 条」与看板 total 一致；简报其余内容为固定模板，非 DB 聚合。
3. **all_tickets 与指标**：指标不依赖 all_tickets 的数值，只依赖 DB；all_tickets 在 DB 为空时来自 CSV，可能导致「列表有数据、指标为 0」。
4. **Hero vs 历史**：Hero 来自 session 当次运行结果；历史来自 DB 最近 50 条且排除 Hero 的 ticket_id，二者数据源不同。
5. **历史按工单不按批次**：历史区按「单条工单」的 created_at 分组，不是按「巡检批次」分组；同一次巡检的多条工单可能分散在不同日期下。

---

*文档版本：基于当前代码梳理，如有逻辑变更请同步更新此文档。*
