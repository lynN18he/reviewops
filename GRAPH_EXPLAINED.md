# ReviewOps 工作流详解：给初学者的完整指南

> 本文档说明 ReviewOps（B2B 电商/物流 SaaS 工单智能分诊）的工作流机制，便于理解代码与数据流。

---

## 1. TicketState 的「追加模式」与「覆盖模式」

### 1.1 什么是「追加」和「覆盖」？

可以把 `TicketState` 想象成一个**状态本**，里面有多类信息（字段）：

- **追加模式**：新内容**接在**旧内容后面，不丢历史
- **覆盖模式**：新内容**整体替换**旧内容，只保留当前批次

### 1.2 在哪里定义？

在 **`src/state.py`** 的 **`reducer`** 中定义合并规则。

```python
# src/state.py

def reducer(state: TicketState, update: TicketState) -> TicketState:
    """合并状态更新"""
    merged = state.copy()

    if "logs" in update:
        merged["logs"] = state.get("logs", []) + update.get("logs", [])

    if "processed_ids" in update:
        existing_ids = set(state.get("processed_ids", []))
        new_ids = set(update.get("processed_ids", []))
        merged["processed_ids"] = list(existing_ids | new_ids)

    if "incr_tickets" in update:
        merged["incr_tickets"] = update.get("incr_tickets", [])

    if "critical_tickets" in update:
        merged["critical_tickets"] = update.get("critical_tickets", [])

    if "rag_analysis_results" in update:
        merged["rag_analysis_results"] = update.get("rag_analysis_results", [])

    if "action_plans" in update:
        merged["action_plans"] = update.get("action_plans", [])

    return merged
```

### 1.3 字段分类总结

| 字段名 | 模式 | 原因 | 示例 |
|--------|------|------|------|
| **`logs`** | ✅ **追加** | 保留完整执行历史，便于排查 | `[旧日志] + [新日志]` |
| **`processed_ids`** | ✅ **并集合并** | 工单 ID 去重，避免重复处理 | `[TIK-051, TIK-052] \| [TIK-053] = [TIK-051, TIK-052, TIK-053]` |
| **`incr_tickets`** | ❌ **覆盖** | 每次 Monitor 只产出「本批」增量工单 | `[工单1, 工单2]` → `[工单3, 工单4]` |
| **`critical_tickets`** | ❌ **覆盖** | Filter 只筛选本批的高危工单 | `[高危1, 高危2]` → `[高危3, 高危4]` |
| **`rag_analysis_results`** | ❌ **覆盖** | RAG 只分析本批工单的归因结果 | `[结果1, 结果2]` → `[结果3, 结果4]` |
| **`action_plans`** | ❌ **覆盖** | Action 只生成本批的行动建议 | `[行动1, 行动2]` → `[行动3, 行动4]` |

### 1.4 为什么这样设计？

- **追加（logs, processed_ids）**  
  - `logs`：保留完整执行轨迹，方便调试与审计。  
  - `processed_ids`：累积已处理工单 ID，保证幂等（同一条工单不重复分诊）。

- **覆盖（其余字段）**  
  - 这些字段表示**当前这一批**的数据，不是全量历史。  
  - 每次运行只处理「本批」新工单，所以用新结果整体替换；例如 `incr_tickets` 表示「本批增量工单」，不是「全部历史工单」。

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
│    1. 优先从 test_tickets_incremental.csv 读取工单（否则从      │
│       test_tickets.csv 读取）                                    │
│    2. 打乱顺序后，按 MIN_TICKETS_PER_BATCH 取本批数量            │
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
- **绑定 reducer**：状态合并按 `src/state.py` 的 `reducer` 执行。  
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
| **数据源** | `test_tickets_incremental.csv`（优先）或 `test_tickets.csv`，格式一致（如 Ticket_ID, User_Message） |
| **持久化** | SQLite `tickets` 表（ticket_id, ticket_content, urgency_level, category） |
| **Monitor** | 从 CSV 随机取本批工单，去重后入库并产出 incr_tickets |
| **Filter** | B2B SaaS 高危标准 + 关键词兜底，产出 critical_tickets |
| **RAG** | L2 智能体 + Tool 调用（ChromaDB 检索），产出归因结论与证据 |
| **Action** | 生成行动建议并回写 DB（含 urgency_level、category） |

---

**希望这份说明能帮助你理解当前项目的工作流与状态设计。** 🚀
