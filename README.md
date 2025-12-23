# ReviewOps - 用户反馈决策中台

一个基于 RAG + LLM 的 B端 SaaS 原型，帮助产品经理分析用户反馈并生成可执行的行动建议。

## ✨ 功能特性

- **智能语义聚类**：使用 LLM 自动发现用户反馈中的主要抱怨点
- **RAG 归因分析**：基于产品说明书进行智能归因，识别问题根源
- **动态行动生成**：根据 RAG 分析结果自动生成针对性的行动计划
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

在项目根目录创建 `.env` 文件，或直接在代码中配置：

```bash
export DASHSCOPE_API_KEY="your-dashscope-api-key"
```

获取 API Key：
1. 访问 https://dashscope.console.aliyun.com/
2. 注册/登录阿里云账号
3. 在 API-KEY 管理页面创建新的 API Key

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
├── app.py              # Streamlit 主应用
├── injest.py           # 数据摄入脚本
├── requirements.txt    # Python 依赖
├── user_reviews.csv    # 用户评论数据
├── dji_spec.pdf        # 产品说明书（PDF）
├── chroma_db/          # 向量数据库（自动生成，已忽略）
└── README.md           # 项目说明
```

## 🔧 技术栈

- **前端框架**：Streamlit
- **数据处理**：Pandas
- **可视化**：Plotly
- **RAG 框架**：LangChain
- **向量数据库**：ChromaDB
- **Embedding 模型**：阿里云 DashScope (text-embedding-v3)
- **LLM 模型**：阿里云千问 (qwen-plus)

## 📊 核心功能

### 1. 数据概览
- 总评论数、平均评分、负面评价占比
- AI 每日简报

### 2. RAG 归因分析
- 自动提取负面评价
- LLM 语义聚类识别主要问题
- 基于产品说明书进行 RAG 检索和归因
- 可视化问题分布（交互式饼图）

### 3. 动态行动生成
- 根据 RAG 归因结论自动生成行动计划
- 支持多种行动类型：
  - 🐞 Jira Ticket（产品缺陷）
  - 📝 Doc Update（文档更新）
  - 📧 Email Draft（客服邮件）
  - 📅 Meeting（会议安排）
- 按优先级自动排序

## 🔒 安全提示

⚠️ **重要**：在提交代码到 GitHub 之前，请确保：

1. 移除所有硬编码的 API Key
2. 使用环境变量或 `.env` 文件管理敏感信息
3. 将 `.env` 添加到 `.gitignore`

## 📝 使用说明

1. **准备数据**：
   - 将用户评论数据放入 `user_reviews.csv`
   - 将产品说明书 PDF 放入项目根目录

2. **构建知识库**：
   ```bash
   python injest.py
   ```

3. **启动应用**：
   ```bash
   streamlit run app.py
   ```

4. **使用流程**：
   - 在侧边栏配置 API Key
   - 点击"开始归因分析"
   - 查看 RAG 分析结果
   - 查看自动生成的行动建议
   - 点击按钮执行相应操作

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

