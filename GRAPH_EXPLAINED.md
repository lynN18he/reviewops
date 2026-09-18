# ReviewOps 工作流详解：给初学者的完整指南

> 本文档说明 ReviewOps（B2B 电商/物流 SaaS 工单智能分诊）的工作流机制，便于理解代码与数据流。

---

## 1. TicketState 与状态流转

### 1.1 TicketState 是什么？

可以把 `TicketState` 想象成 LangGraph 节点之间传递的**状态本**，里面记录本轮巡检的工单、RAG 结果、路由结果、行动建议和日志。

### 1.2 在哪里定义？

状态字段定义在 **`src/state.py`** 的 **`TicketState`** 中。当前 `src/graph.py` 使用 `StateGraph(TicketState)`；节点返回的字典会由 LangGraph 合并到当前状态中。需要累积的内容（例如多类 action plan）由节点自身读取当前 state 后追加返回。

### 1.3 字段分类总结

| 字段名 | 当前语义 | 原因 | 示例 |
|--------|------|------|------|
| **`logs`** | 节点运行日志 | 供 UI 实时展示本轮流水线过程 | `["monitor 日志", "filter 日志"]` |
| **`processed_ids`** | 本轮已拉取/处理 ID | 工单 ID 去重，避免同一轮重复处理 | `[INC-001, INC-002]` |
| **`incr_tickets`** | 本轮 monitor 产出的工单 | 每次运行只代表当前批次 | `[本批工单1, 本批工单2]` |
| **`critical_tickets`** | 本轮高危工单 | Filter 只筛选当前批次 | `[高危1, 高危2]` |
| **`rag_analysis_results`** | 本轮 RAG 归因结果 | RAG 只分析当前批次的高危工单 | `[结果1, 结果2]` |
| **`action_plans`** | 本轮行动建议 | 各 action 节点在当前 state 基础上追加后返回 | `[邮件建议, Jira 建议]` |

### 1.4 为什么这样设计？

- 大多数字段表示**当前这一批**的数据，不是全量历史。
- 长期结果以 SQLite 为准：`tickets` 保存工单分析结果，`workflow_meta` / `workflow_runs` 保存巡检游标、上次运行时间和批次流水账；`st.session_state` 只作为页面渲染缓存。
- `action_plans` 需要跨多个 action 节点累积，因此各 action 节点会读取已有 `state["action_plans"]` 后再追加本节点结果。

---

## 2. 完整工作流流程图（ASCII）

下面按步骤标出各节点对 State 的读写与变化：

```
┌─────────────────────────────────────────────────────────────────┐
│                    初始状态 (Initial State)                      │
│  State = {                                                       │
│    incr_tickets: [],                                             │
│    critical_tickets: [],                                          │
│    rag_analysis_results: [],                                     │
│    action_plans: [],                                             │
│    logs: [],                                                     │
│    processed_ids: [TIK-051, TIK-052, ...]  ← 保留历史已处理 ID   │
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    [用户点击「运行智能工作流」]
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  📡 Monitor Node (node_monitor)                                  │
│  ─────────────────────────────────────────────────────────────  │
│  输入: state.processed_ids = [TIK-051, TIK-052, ...]            │
│                                                                  │
│  处理:                                                           │
│    1. 优先从 incremental_tickets.csv 按 Batch_ID 读取整批工单   │
│       （否则从 cold_start_tickets.csv 读取）                     │
│    2. 增量模式下按批次顺序读取；非增量回退时按配置限制数量       │
│    3. 过滤：已存在于 DB 或 processed_ids 的工单跳过              │
│    4. 写入 SQLite（tickets 表），并生成本批 incr_tickets         │
│                                                                  │
│  输出:                                                           │
│    {                                                             │
│      incr_tickets: [工单A, 工单B],      ← 覆盖                  │
│      processed_ids: [TIK-053, TIK-054],  ← 并集合并（新 ID）     │
│      logs: ["📅 工单输入源：... | 本次新增 2 条工单"]  ← 追加    │
│    }                                                             │
│                                                                  │
│  State 变化:                                                     │
│    ✅ incr_tickets: [] → [工单A, 工单B]  (覆盖)                  │
│    ✅ processed_ids: [TIK-051,052] → [..., TIK-053, TIK-054]     │
│    ✅ logs: [] → ["📅 ... 本次新增 2 条工单"]  (追加)            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  🔍 Filter Node (node_filter)                                    │
│  ─────────────────────────────────────────────────────────────  │
│  输入: state.incr_tickets = [工单A, 工单B]                        │
│                                                                  │
│  处理:                                                           │
│    1. 构建 B2B SaaS 高危工单筛选 Prompt（核心业务阻断、系统级   │
│       报错、高情绪资损等）                                        │
│    2. 调用 LLM 返回 critical_ticket_ids；失败时用关键词兜底     │
│       （502、504、白屏、宕机、全不更新、无法登陆等）             │
│    3. 按 ID 匹配出本批高危工单列表                              │
│                                                                  │
│  输出:                                                           │
│    {                                                             │
│      critical_tickets: [工单A],        ← 覆盖（筛选结果）        │
│      logs: ["🔍 筛选节点：... 筛选出 1 条高危工单"]  ← 追加      │
│    }                                                             │
│                                                                  │
│  State 变化:                                                     │
│    ✅ critical_tickets: [] → [工单A]  (覆盖)                     │
│    ✅ logs: [旧日志] → [旧日志, "🔍 ... 1 条高危工单"]  (追加)   │
│    ⚠️ incr_tickets: [工单A, 工单B]  (不变，后续节点不再使用)    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    [条件判断: 是否有高危工单?]
                              ↓
                    ┌─────────┴─────────┐
                    │                   │
            [有高危工单]          [无高危工单]
                    │                   │
                    ↓                   ↓
┌─────────────────────────────────┐   ┌──────────────────────┐
│  📄 RAG Node (node_rag_analysis) │   │  直接结束 (END)       │
│  ───────────────────────────────│   │                      │
│  输入: state.critical_tickets    │   │  State 保持 Filter   │
│        = [工单A]                 │   │  节点的输出不变      │
│                                  │   └──────────────────────┘
│  处理:                           │
│    1. 对每条高危工单调用 L2 智能体（Tool 调用）                  │
│    2. 工具：search_known_issues / search_release_notes /       │
│       search_api_docs_and_sop（基于 ChromaDB 相似度检索）       │
│    3. 模型根据工具返回做归因，输出 conclusion / reason / evidence│
│                                                                  │
│  输出:                           │
│    {                             │
│      rag_analysis_results: [     │
│        {                         │
│          ticket_id: "TIK-054",    │
│          conclusion: "✅ 配置问题",│
│          reason: "分析原因...",   │
│          evidence: "证据片段..."  │
│        }                         │
│      ],                          │
│      logs: ["📄 完成 N 条工单的归因分析（已使用 Tool 调用）"]    │
│    }                             │
│                                  │
│  State 变化:                     │
│    ✅ rag_analysis_results: [] →  │
│       [{ conclusion, reason, evidence, ... }]                   │
│    ✅ logs: [旧日志] → [旧日志, "📄 完成 N 条工单的归因分析"]   │
│    ⚠️ critical_tickets: [工单A]  (不变，后续节点不再使用)        │
└─────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────────────┐
│  💡 Action Node (node_action_gen)                                │
│  ─────────────────────────────────────────────────────────────  │
│  输入: state.rag_analysis_results = [{ conclusion, reason, ... }]│
│                                                                  │
│  处理:                                                           │
│    1. 根据归因结果构建行动生成 Prompt                             │
│    2. 调用 LLM 生成 JSON（action_type, title, content, priority）│
│    3. 根据 priority 映射 risk_level / urgency_level（P0/P1/P2）│
│    4. 写回 SQLite：更新 rag_result、action_plan、urgency_level、│
│       category 等                                               │
│                                                                  │
│  输出:                                                           │
│    {                                                             │
│      action_plans: [                                            │
│        {                                                         │
│          ticket_id: "TIK-054",                                   │
│          action_type: "Jira Ticket",                            │
│          title: "处理工单 TIK-054 的问题",                       │
│          content: "详细内容...",                                 │
│          priority: "High"                                        │
│        }                                                         │
│      ],                                                          │
│      logs: ["💡 行动生成节点：生成 N 个行动建议 | ✅ 已更新..."]  │
│    }                                                             │
│                                                                  │
│  State 变化:                                                     │
│    ✅ action_plans: [] → [{ Jira Ticket, High, ... }]  (覆盖)    │
│    ✅ logs: [旧日志] → [旧日志, "💡 生成 N 个行动建议"]  (追加)  │
│    ⚠️ rag_analysis_results: [...]  (不变，不再使用)              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    最终状态 (Final State)                        │
│  State = {                                                       │
│    incr_tickets: [工单A, 工单B],       ← Monitor 输出           │
│    critical_tickets: [工单A],         ← Filter 输出             │
│    rag_analysis_results: [{ conclusion, ... }],                 │
│    action_plans: [{ Jira Ticket, High, ... }],                  │
│    logs: [                                                        │
│      "📅 ... 本次新增 2 条工单",       ← Monitor 日志            │
│      "🔍 ... 筛选出 1 条高危工单",     ← Filter 日志             │
│      "📄 完成 N 条工单的归因分析",     ← RAG 日志                │
│      "💡 生成 N 个行动建议"            ← Action 日志             │
│    ],                                                             │
│    processed_ids: [..., TIK-053, TIK-054]  ← 累积已处理工单 ID  │
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
```

### 2.1 关键观察

1. **数据流**  
   `incr_tickets` → `critical_tickets` → `rag_analysis_results` → `action_plans`，节点之间只传递本批数据，不混入历史批次。

2. **状态累积**  
   - `logs`、`processed_ids` 为**累积**，每次运行追加。  
   - 其余字段为**覆盖**，只表示本批结果。

3. **条件分支**  
   Filter 之后若无高危工单，直接 **END**，不执行 RAG 与 Action。

4. **持久化**  
   - Monitor：新工单写入 SQLite `tickets` 表。  
   - Action：同表更新 `rag_result`、`action_plan`、`urgency_level`、`category`。
   - UI：工作流完成后写入 `workflow_meta` / `workflow_runs`，用于刷新或重启后恢复巡检状态。

---

## 3. `compile()` 在做什么？

### 3.1 直观理解

`compile()` 把「图定义」变成「可执行的工作流」：

- **图定义** = `StateGraph(TicketState)` + 节点与边  
- **可执行工作流** = `graph_app`，能对初始状态做 `stream()` / `invoke()`

### 3.2 代码位置

```python
# src/graph.py

def build_graph():
    workflow = StateGraph(TicketState)

    workflow.add_node("monitor", node_monitor)
    workflow.add_node("filter", node_filter)
    workflow.add_node("rag_analysis", node_rag_analysis)
    workflow.add_node("action_gen", node_action_gen)

    workflow.set_entry_point("monitor")
    workflow.add_edge("monitor", "filter")
    workflow.add_conditional_edges(
        "filter",
        should_continue_analysis,   # 有 critical_tickets 则走 rag_analysis，否则 end
        { "rag_analysis": "rag_analysis", "end": END }
    )
    workflow.add_edge("rag_analysis", "action_gen")
    workflow.add_edge("action_gen", END)

    graph_app = workflow.compile()
    return graph_app
```

### 3.3 `compile()` 的作用

- **校验图**：入口、连通性、条件边合法等。  
- **生成执行计划**：从 monitor 开始，按边与条件决定下一步节点。  
- **合并节点输出**：节点返回的状态字段由 LangGraph 合并；需要累积的列表由节点自身读取旧 state 后追加返回。  
- **得到可复用对象**：同一 `graph_app` 可多次 `stream(invoke)`，无需重新建图。

### 3.4 使用方式示例

```python
# 1. 初始状态（可保留历史 processed_ids）
initial_state = {
    "incr_tickets": [],
    "critical_tickets": [],
    "rag_analysis_results": [],
    "action_plans": [],
    "logs": [],
    "processed_ids": []  # 或保留上一轮已处理工单 ID
}

# 2. 流式执行
for event in graph_app.stream(initial_state):
    for node_name, node_output in event.items():
        print(f"节点 {node_name} 执行完成，输出: {node_output}")

# 3. 或一次性执行
final_state = graph_app.invoke(initial_state)
```

---

## 4. 总结

### 4.1 概念回顾

1. **追加 vs 覆盖**  
   - 追加：`logs`、`processed_ids`（保留历史、幂等）。  
   - 覆盖：`incr_tickets`、`critical_tickets`、`rag_analysis_results`、`action_plans`（仅本批）。

2. **数据流**  
   Monitor → Filter →（若有高危）→ RAG → Action；每步只依赖上一步的本批输出。

3. **compile()**  
   将 `StateGraph` 编译为可执行的 `graph_app`，负责校验、执行计划和状态合并。

### 4.2 与当前架构的对应关系

| 组件 | 说明 |
|------|------|
| **数据源** | `incremental_tickets.csv`（优先，按 `Batch_ID`）或 `cold_start_tickets.csv`，格式一致（如 Ticket_ID, User_Message） |
| **持久化** | SQLite `tickets` 表保存工单结果；`workflow_meta` / `workflow_runs` 保存巡检状态 |
| **Monitor** | 从增量 CSV 按批次读取工单，去重后入库并产出 incr_tickets |
| **Filter** | B2B SaaS 高危标准 + 关键词兜底，产出 critical_tickets |
| **RAG** | L2 智能体 + Tool 调用（ChromaDB 检索），产出归因结论与证据 |
| **Action** | 生成行动建议并回写 DB（含 urgency_level、category） |

---

**希望这份说明能帮助你理解当前项目的工作流与状态设计。** 🚀
