"""
依赖安装（在项目根目录执行）：
pip install -U langchain langchain-community chromadb pypdf tiktoken python-dotenv dashscope

API Key 设置方式（使用阿里千问）：
export DASHSCOPE_API_KEY="your-dashscope-api-key"

或者创建 .env 文件：
DASHSCOPE_API_KEY=your-dashscope-api-key

获取阿里千问 API Key：
1. 访问 https://dashscope.console.aliyun.com/
2. 注册/登录阿里云账号
3. 在 API-KEY 管理页面创建新的 API Key
"""

import os
import sys
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_community.vectorstores import Chroma


def ensure_api_key():
    """确保 DASHSCOPE_API_KEY 存在，否则给出友好提示"""
    api_key = "sk-bde9ea0d21a74948bd72fd113f928605"
    if not api_key:
        raise EnvironmentError(
            "❌ 未检测到 DASHSCOPE_API_KEY 环境变量！\n"
            "\n"
            "请设置阿里千问 API Key：\n"
            "  export DASHSCOPE_API_KEY='your-api-key'\n"
            "\n"
            "或者创建 .env 文件并添加：\n"
            "  DASHSCOPE_API_KEY=your-api-key\n"
            "\n"
            "获取 API Key：\n"
            "  访问 https://dashscope.console.aliyun.com/ 注册并创建 API Key"
        )
    return api_key


def get_embeddings():
    """获取 Embeddings 实例，使用阿里千问（通义千问）的 embedding 服务"""
    # ensure_api_key()
    api_key = "sk-bde9ea0d21a74948bd72fd113f928605"
    print("🔌 正在连接阿里千问 Embedding 服务...")
    
    # 使用 DashScopeEmbeddings（阿里千问官方 embedding 接口）
    # text-embedding-v1: 通用 embedding 模型
    # text-embedding-v2: 增强版 embedding 模型
    # text-embedding-v3: 最新版 embedding 模型（推荐）
    return DashScopeEmbeddings(
        model="text-embedding-v3",  # 阿里千问最新 embedding 模型，支持多语言
        # dashscope_api_key=os.getenv("DASHSCOPE_API_KEY")
        dashscope_api_key=api_key
    )


def ingest_documents(
    pdf_path: str = "dji_spec.pdf",
    persist_directory: str = "./chroma_db",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
):
    print("🚀 开始构建 RAG 知识库...")

    # 1) 检查文件
    if not os.path.exists(pdf_path):
        print(f"❌ 错误：找不到文件 {pdf_path}")
        sys.exit(1)

    # 2) 加载 PDF
    print(f"📄 正在读取 PDF: {pdf_path} ...")
    loader = PyPDFLoader(pdf_path)
    pages = loader.load()
    print(f"✅ PDF 加载完成，共 {len(pages)} 页")

    # 3) 语义切分
    print("✂️ 正在进行语义切分...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
    )
    chunks = splitter.split_documents(pages)
    print(f"✅ 切分完成，共生成 {len(chunks)} 个 chunks")

    # 4) 向量化并写入 ChromaDB
    print("🔑 正在检查 API Key ...")
    embeddings = get_embeddings()

    print(f"🔢 正在向量化并写入 ChromaDB 到 {persist_directory} ...")

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_directory,
    )
    vectorstore.persist()

    print(f"🎉 成功！知识库已保存至 {persist_directory}")
    print("👉 下一步：可以运行 app.py 连接此向量库进行检索。")


if __name__ == "__main__":
    try:
        ingest_documents()
    except Exception as e:
        print(f"❌ 运行失败：{e}")
        sys.exit(1)

