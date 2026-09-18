# 单元测试说明

## 测试结构

```
tests/
├── __init__.py
├── conftest.py              # Pytest 配置和共享 fixtures
├── test_state.py            # 状态字段和路由枚举测试
├── test_config.py           # 配置管理测试
├── test_utils.py            # 工具函数测试
├── test_tools.py            # RAG Tool metadata filter 测试
├── test_injest_metadata.py  # 知识库 metadata 归类测试
├── test_database_workflow.py # 工作流状态持久化测试
├── test_graph.py            # 工作流图构建测试
├── test_nodes_monitor.py    # 监控节点测试
├── test_nodes_filter.py     # 筛选节点测试
├── test_nodes_rag.py        # RAG 分析节点测试
└── test_nodes_action.py     # 行动生成节点测试
```

## 运行测试

### 安装测试依赖

```bash
pip install -r requirements.txt
```

### 运行所有测试

```bash
pytest
```

### 运行特定测试文件

```bash
pytest tests/test_state.py
pytest tests/test_config.py
pytest tests/test_nodes_monitor.py
```

### 运行特定测试类

```bash
pytest tests/test_state.py::TestTicketState
```

### 运行特定测试函数

```bash
pytest tests/test_state.py::TestTicketState::test_ticket_state_accepts_current_graph_fields
```

### 查看测试覆盖率

```bash
pytest --cov=src --cov-report=html
```

生成的覆盖率报告在 `htmlcov/index.html`

### 详细输出

```bash
pytest -v
```

### 显示打印输出

```bash
pytest -s
```

## 测试覆盖

### ✅ 已覆盖的模块

1. **src/state.py**
   - ✅ 当前工作流状态字段
   - ✅ 诊断路由枚举

2. **src/config.py**
   - ✅ 所有配置类的默认值
   - ✅ 环境变量读取
   - ✅ API Key 验证

3. **src/utils.py**
   - ✅ LLM 初始化成功场景
   - ✅ API Key 缺失时的错误处理

4. **src/graph.py**
   - ✅ 条件路由函数（should_continue_analysis）
   - ✅ 图构建函数（build_graph）

5. **src/nodes/monitor.py**
   - ✅ 从增量 CSV 按 `Batch_ID` 顺序读取工单
   - ✅ 空文件/无工单处理
   - ✅ 幂等性检查
   - ✅ 日志格式

6. **src/nodes/filter.py**
   - ✅ 空工单列表处理
   - ✅ LLM 筛选成功场景
   - ✅ LLM 失败时的关键词降级逻辑

7. **src/nodes/rag.py**
   - ✅ 空高危工单处理
   - ✅ LLM RAG 分析成功场景
   - ✅ JSON 解析错误处理

8. **src/nodes/action.py**
   - ✅ 空归因结果处理
   - ✅ LLM 生成行动成功场景
   - ✅ JSON 解析错误时的默认值使用

9. **src/tools.py / injest.py**
   - ✅ RAG Tool 按 `doc_type` 传递 Chroma metadata filter
   - ✅ SOP / 发版 / Jira 知识 chunk 的 metadata 归类

10. **src/services/database.py**
   - ✅ `monitor_next_batch_id` 与 `last_run_time` 持久化
   - ✅ 巡检批次流水账写入与倒序读取

## 测试策略

### Mock 策略

- **LLM 调用**：使用 `unittest.mock` 模拟 LLM 响应，避免实际 API 调用
- **环境变量**：使用 `conftest.py` 中的 fixture 自动 mock 环境变量
- **向量数据库**：RAG 测试中不实际初始化向量库，测试降级逻辑

### 测试原则

1. **独立性**：每个测试独立运行，不依赖其他测试
2. **可重复性**：测试结果可重复，不依赖外部状态
3. **快速执行**：使用 mock 避免慢速操作（API 调用、文件 I/O）
4. **边界测试**：测试空值、错误情况、边界条件

## 持续集成

建议在 CI/CD 流程中添加测试：

```yaml
# .github/workflows/test.yml 示例
- name: Run tests
  run: |
    pip install -r requirements.txt
    pytest --cov=src --cov-report=xml
```

## 注意事项

1. **API Key**：测试使用 mock，不需要真实的 API Key
2. **向量数据库**：RAG 测试不实际创建向量库，测试降级逻辑
3. **时间依赖**：monitor 节点测试可能因时间戳不同而略有差异，这是正常的
4. **批次顺序**：monitor 节点按 `Batch_ID` 顺序读取增量工单，测试应保持确定性

