"""Matplotlib 教学助手与 MCP 服务共享配置。

集中管理项目路径、环境变量、模型、MCP、Redis、索引和上下文预算。
本模块只读取配置，不初始化模型、数据库连接或 Streamlit UI。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv


# -----------------------------------------------------------------------------
# 项目路径与环境变量文件
# -----------------------------------------------------------------------------
# 以 config.py 所在目录作为项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parent
BASE_DIR = PROJECT_ROOT
API_KEY_DIR = (PROJECT_ROOT / "API_Key_and_Tools").resolve()

DEEPSEEK_ENV_PATH = (API_KEY_DIR / "Deepseek_API_Key.env").resolve()

# 兼容原始代码中的变量名称。
ENV_FILE_PATH = DEEPSEEK_ENV_PATH

MCP_TOKEN_SECRET_ENV_PATH = (
    API_KEY_DIR / "MCP_TOKEN_SECRET.env"
).resolve()

SERPAPI_ENV_PATH = (
    API_KEY_DIR / "SERPAPI_API_Key.env"
).resolve()

# 必须在加载相关模型依赖前设置 Hugging Face 镜像。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 加载共享环境变量。
# 默认不覆盖进程中已经显式设置的环境变量。
load_dotenv(MCP_TOKEN_SECRET_ENV_PATH, override=False)
load_dotenv(DEEPSEEK_ENV_PATH, override=False)

if SERPAPI_ENV_PATH.is_file():
    load_dotenv(SERPAPI_ENV_PATH, override=False)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
MCP_TOKEN_SECRET = os.getenv("MCP_TOKEN_SECRET", "")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")


# -----------------------------------------------------------------------------
# 模型配置
# -----------------------------------------------------------------------------
TEXT_MODEL_NAME = os.getenv(
    "TEXT_MODEL_NAME",
    "deepseek-v4-flash",
)

TEXT_SUMMARY_MODEL = os.getenv(
    "TEXT_SUMMARY_MODEL",
    TEXT_MODEL_NAME,
)

TEXT_MODEL_BASE_URL = os.getenv(
    "TEXT_MODEL_BASE_URL",
    "https://api.deepseek.com/v1",
)

TEXT_MODEL_TEMPERATURE = float(
    os.getenv("TEXT_MODEL_TEMPERATURE", "0")
)

# 当前 Embedding 模型
EMBEDDING_MODEL_PATH = Path(
    os.getenv(
        "EMBEDDING_MODEL_PATH",
        str(
            PROJECT_ROOT
            / "embedding_models"
            / "text2vec-base-chinese"
        ),
    )
).expanduser()

EMBEDDING_MODEL = str(EMBEDDING_MODEL_PATH)

# 可选视觉模型。
VISION_MODEL = os.getenv("VISION_MODEL", "")
VISION_MODEL_BASE_URL = os.getenv(
    "VISION_MODEL_BASE_URL", ""
)
VISION_API_KEY = os.getenv("VISION_API_KEY", "")

ENABLE_MODEL_ENRICHMENT = os.getenv(
    "ENABLE_MODEL_ENRICHMENT", "1"
).strip().lower() not in {"0", "false", "no"}

INDEX_WORKERS = max(
    1,
    int(os.getenv("PDF_INDEX_WORKERS", "3")),
)


# -----------------------------------------------------------------------------
# MCP 服务与鉴权配置
# -----------------------------------------------------------------------------
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_PATH = os.getenv("MCP_PATH", "/mcp")

MCP_SERVER_URL = (
    f"http://{MCP_HOST}:{MCP_PORT}{MCP_PATH}"
)

KNOWLEDGE_BASE_ID = os.getenv(
    "MATPLOTLIB_KNOWLEDGE_BASE_ID",
    "matplotlib-course-v1",
)

MCP_TOKEN_AUDIENCE = os.getenv(
    "MCP_TOKEN_AUDIENCE",
    "matplotlib-course-mcp",
)

MCP_REQUIRED_SCOPE = os.getenv(
    "MCP_REQUIRED_SCOPE",
    "knowledge:read",
)

MCP_TOKEN_TTL_SECONDS = max(
    300,
    int(os.getenv("MCP_TOKEN_TTL_SECONDS", "3600")),
)

IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z0-9_.@-]{1,128}$"
)


# -----------------------------------------------------------------------------
# 用户认证与知识库权限
# -----------------------------------------------------------------------------
APP_USER_TOKENS_JSON = os.getenv(
    "APP_USER_TOKENS_JSON",
    "{}",
)

APP_USER_KB_ACCESS_JSON = os.getenv(
    "APP_USER_KB_ACCESS_JSON",
    "{}",
)


# -----------------------------------------------------------------------------
# Redis 与会话记忆配置
# -----------------------------------------------------------------------------
REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://localhost:6379/0",
)

REDIS_TTL_SECONDS = max(
    300,
    int(os.getenv("REDIS_TTL_SECONDS", "604800")),
)

REDIS_KEY_PREFIX = os.getenv(
    "REDIS_KEY_PREFIX",
    "rag_chat:v2",
)


# -----------------------------------------------------------------------------
# 模型上下文与历史压缩预算
# -----------------------------------------------------------------------------
MODEL_CONTEXT_TOKENS = max(
    32768,
    int(os.getenv("MODEL_CONTEXT_TOKENS", "131072")),
)

OUTPUT_RESERVE_TOKENS = max(
    1024,
    int(os.getenv("OUTPUT_RESERVE_TOKENS", "8192")),
)

SAFETY_MARGIN_TOKENS = max(
    2048,
    int(os.getenv("CONTEXT_SAFETY_MARGIN_TOKENS", "8192")),
)

SYSTEM_RESERVE_TOKENS = max(
    2048,
    int(os.getenv("SYSTEM_RESERVE_TOKENS", "8192")),
)

MAX_CONTEXT_INPUT_TOKENS = max(
    8192,
    MODEL_CONTEXT_TOKENS
    - OUTPUT_RESERVE_TOKENS
    - SAFETY_MARGIN_TOKENS
    - SYSTEM_RESERVE_TOKENS,
)

CONTEXT_INPUT_BUDGET_TOKENS = min(
    MAX_CONTEXT_INPUT_TOKENS,
    max(
        8192,
        int(
            os.getenv(
                "CONTEXT_INPUT_BUDGET_TOKENS",
                str(MAX_CONTEXT_INPUT_TOKENS),
            )
        ),
    ),
)

HISTORY_TARGET_TOKENS = min(
    CONTEXT_INPUT_BUDGET_TOKENS,
    max(
        8192,
        int(os.getenv("HISTORY_TARGET_TOKENS", "65536")),
    ),
)

SUMMARY_INPUT_TOKENS = max(
    2048,
    int(os.getenv("SUMMARY_INPUT_TOKENS", "12000")),
)

SUMMARY_OUTPUT_TOKENS = max(
    512,
    int(os.getenv("SUMMARY_OUTPUT_TOKENS", "2048")),
)

MAX_HISTORY_MESSAGES = max(
    12,
    int(os.getenv("MAX_HISTORY_MESSAGES", "80")),
)

MIN_RECENT_TURNS = max(
    1,
    int(os.getenv("MIN_RECENT_TURNS", "2")),
)

TOKEN_ESTIMATE_CHARS_PER_TOKEN = max(
    1.5,
    float(os.getenv("TOKEN_ESTIMATE_CHARS_PER_TOKEN", "3.0")),
)

MAX_TOOL_MESSAGE_TOKENS = max(
    1024,
    int(os.getenv("MAX_TOOL_MESSAGE_TOKENS", "12000")),
)


# -----------------------------------------------------------------------------
# 原 MCP 服务端的 PDF、OCR、索引路径
#
# 当前 PDF、Embedding、Tesseract 和 Poppler 仍位于原来的本地目录。
# MCP 服务端迁入本项目后，索引目录将跟随 PROJECT_ROOT 迁移。
# -----------------------------------------------------------------------------

DATA_DIRECTORY = PROJECT_ROOT / "data"

PDF_FILE_PATHS = (
    DATA_DIRECTORY / "第一回：Matplotlib初识.pdf",
    DATA_DIRECTORY / "第二回：艺术画笔见乾坤.pdf",
    DATA_DIRECTORY / "第三回：布局格式定方圆.pdf",
)

SECOND_CHAPTER_FILENAME = "第二回：艺术画笔见乾坤.pdf"

TESSERACT_CMD = Path(r"D:\OCR_loader\tesseract.exe")

POPPLER_PATH = Path(
    r"D:\poppler\poppler-26.02.0\Library\bin"
)

INDEX_SCHEMA_VERSION = "multivector-v2"

INDEX_ROOT = (
    PROJECT_ROOT
    / "docs"
    / "multivector"


    / "matplotlib_v2"
)

CHROMA_DIRECTORY = INDEX_ROOT / "chroma"
DOCSTORE_DIRECTORY = INDEX_ROOT / "docstore"
ASSET_DIRECTORY = INDEX_ROOT / "assets"
MODEL_CACHE_DIRECTORY = INDEX_ROOT / "model_cache"
MANIFEST_PATH = INDEX_ROOT / "index_manifest.json"


# -----------------------------------------------------------------------------
# RAG Fusion、Retriever 与 Agent 参数
# -----------------------------------------------------------------------------
FUSION_QUERY_COUNT = 3
FUSION_RESULTS_PER_QUERY = 8
FUSION_RRF_K = 60
FUSION_TOP_K = 8

RETRIEVER_K = 8
RETRIEVER_FETCH_K = 32
RETRIEVER_LAMBDA_MULT = 0.55

MAX_AGENT_STEPS = max(
    1,
    int(os.getenv("MAX_AGENT_STEPS", "6")),
)

TOOL_ROUTER_COLLECTION_NAME = (
    "react_agent_tool_router_v1"
)

REQUIRED_MCP_TOOLS = frozenset(
    {
        "search_matplotlib_knowledge",
        "list_matplotlib_course_documents",
    }
)