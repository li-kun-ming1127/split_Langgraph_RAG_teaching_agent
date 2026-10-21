"""模型、Embedding、MCP 客户端和工具选择服务。

本模块从 config.py 读取共享配置，从 auth.py 获取 MCP 身份令牌；
不负责 Streamlit 页面布局，也不构建 LangGraph Agent 工作流。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import nest_asyncio
import streamlit as st
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.example_selectors import SemanticSimilarityExampleSelector
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI

from auth import SessionContext, create_mcp_context_token
from config import (
    DEEPSEEK_API_KEY,
    EMBEDDING_MODEL,
    MCP_SERVER_URL,
    MCP_TOKEN_TTL_SECONDS,
    OUTPUT_RESERVE_TOKENS,
    REQUIRED_MCP_TOOLS,
    TEXT_MODEL_BASE_URL,
    TEXT_MODEL_NAME,
    TEXT_MODEL_TEMPERATURE,
    TOOL_ROUTER_COLLECTION_NAME,
)

LOGGER = logging.getLogger(__name__)

# 保留原始项目的事件循环兼容设置。MCP tools 是异步工具，调用时应使用 ainvoke。
nest_asyncio.apply()


@dataclass
class AgentServices:
    """供 Agent 层使用的依赖集合。

    ToolRouter 和 MCP tools 不做跨用户的全局缓存，避免不同用户的 MCP
    Authorization header / SessionContext 被意外共享。
    """

    text_llm: ChatOpenAI
    embedding: HuggingFaceEmbeddings
    tools: list[Any]
    tool_router: "ToolRouter"
    example_selector: SemanticSimilarityExampleSelector


@st.cache_resource(show_spinner="正在加载中文嵌入模型...")
def get_embedding() -> HuggingFaceEmbeddings:
    """加载并缓存本地中文 Embedding 模型。"""
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


@st.cache_resource(show_spinner=False)
def get_text_llm() -> ChatOpenAI:
    """初始化并复用 DeepSeek 文本/工具调用模型。"""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError(
            "未读取到 DEEPSEEK_API_KEY，请检查 API_Key_and_Tools/Deepseek_API_Key.env。"
        )

    return ChatOpenAI(
        model=TEXT_MODEL_NAME,
        api_key=DEEPSEEK_API_KEY,
        base_url=TEXT_MODEL_BASE_URL,
        temperature=TEXT_MODEL_TEMPERATURE,
        max_tokens=OUTPUT_RESERVE_TOKENS,
    )


async def _discover_mcp_tools(
    context: SessionContext,
    token_window: int,
) -> list[Any]:
    """使用当前用户/会话签发的 HMAC Token 发现 MCP 工具。"""
    context_token = create_mcp_context_token(context, token_window)
    client = MultiServerMCPClient(
        {
            "matplotlib_knowledge": {
                "url": MCP_SERVER_URL,
                "transport": "streamable_http",
                "headers": {
                    "Authorization": f"Bearer {context_token}",
                },
            }
        }
    )
    return await client.get_tools()


def _run_coroutine_in_new_loop(coroutine: Any) -> Any:
    """在独立事件循环中运行协程，并在结束后清理循环。"""
    previous_loop: asyncio.AbstractEventLoop | None
    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()
        # 尽量恢复调用前的事件循环状态，而不是留下一个已关闭的 loop。
        try:
            if previous_loop is not None and not previous_loop.is_closed():
                asyncio.set_event_loop(previous_loop)
            else:
                asyncio.set_event_loop(None)
        except RuntimeError:
            asyncio.set_event_loop(None)


def _sync_discover_mcp_tools(
    context: SessionContext,
    token_window: int,
) -> list[Any]:
    """同步封装 MCP 工具发现过程，供 Streamlit 同步入口使用。"""
    return _run_coroutine_in_new_loop(
        _discover_mcp_tools(context, token_window)
    )


def run_coroutine_sync(coroutine: Any) -> Any:
    """在 Streamlit 同步脚本中运行异步 Agent/MCP 调用。"""
    return _run_coroutine_in_new_loop(coroutine)


@st.cache_resource(show_spinner="正在连接本机 MCP 知识库服务...")
def get_mcp_tools(
    context: SessionContext,
    token_window: int,
) -> list[Any]:
    """发现并验证当前会话可用的 MCP 工具。

    SessionContext 和 token_window 都参与 Streamlit 缓存键，令牌时间窗口更新后
    会重新发现工具；不同用户/会话不会共用同一组 MCP Tool 对象。
    """
    discovered_tools = _sync_discover_mcp_tools(context, token_window)
    if not discovered_tools:
        raise RuntimeError("MCP 服务未返回任何可用工具。")

    available_names = {tool.name for tool in discovered_tools}
    missing_tools = set(REQUIRED_MCP_TOOLS) - available_names
    if missing_tools:
        raise RuntimeError(
            "MCP 服务缺少必要工具：" + ", ".join(sorted(missing_tools))
        )

    return discovered_tools


class ToolRouter:
    """依据用户问题语义选择当前 Agent 可用的 MCP 工具。

    行为沿用原始单 Agent 版本：保留 search_matplotlib_knowledge 作为核心检索工具，
    并通过独立 Chroma collection 对工具名称和说明进行语义匹配。
    """

    CORE_TOOL_NAMES = frozenset({"search_matplotlib_knowledge"})

    def __init__(
        self,
        available_tools: list[Any],
        embeddings: HuggingFaceEmbeddings,
    ) -> None:
        self.tools = {tool.name: tool for tool in available_tools}
        self._all_names = tuple(sorted(self.tools))

        tool_documents = [
            Document(
                page_content=f"{tool.name}\n{tool.description or ''}",
                metadata={
                    "tool_name": tool.name,
                    "catalog": "agent_tool_router_v1",
                },
            )
            for tool in available_tools
        ]

        self.vectorstore = Chroma(
            collection_name=TOOL_ROUTER_COLLECTION_NAME,
            embedding_function=embeddings,
        )
        if tool_documents and self.vectorstore._collection.count() == 0:
            self.vectorstore.add_documents(tool_documents)

    @property
    def all_names(self) -> tuple[str, ...]:
        """返回当前 ToolRouter 持有的所有工具名称。"""
        return self._all_names

    def select_tool_names(self, query: str) -> list[str]:
        """返回语义相关工具，并保留核心知识检索工具。"""
        if not query.strip() or not self.tools:
            return list(self._all_names)

        try:
            matches = self.vectorstore.similarity_search(
                query,
                k=min(3, len(self.tools)),
            )
            selected = {
                str(document.metadata.get("tool_name"))
                for document in matches
                if document.metadata.get("tool_name") in self.tools
            }
        except Exception:
            LOGGER.exception("ToolRouter 检索失败，回退到当前可用工具集合")
            return list(self._all_names)

        selected.update(
            name for name in self.CORE_TOOL_NAMES if name in self.tools
        )
        return [name for name in self._all_names if name in selected] or list(
            self._all_names
        )

    def resolve(
        self,
        names: list[str] | tuple[str, ...] | None,
    ) -> list[Any]:
        """将 State 中的工具名称解析成工具对象。"""
        valid = [name for name in (names or ()) if name in self.tools]
        if not valid:
            # 与原始单 Agent 版本一致：没有有效名称时回退到当前可用工具集合。
            valid = list(self._all_names)
        return [self.tools[name] for name in valid]


def create_tool_router(
    available_tools: list[Any],
    embeddings: HuggingFaceEmbeddings | None = None,
) -> ToolRouter:
    """创建与给定 MCP Tool 集合绑定的 ToolRouter。"""
    return ToolRouter(available_tools, embeddings or get_embedding())


@st.cache_resource(show_spinner=False)
def get_example_selector() -> SemanticSimilarityExampleSelector:
    """构建 Matplotlib 教学场景的语义相似示例选择器。"""
    examples = [
        {
            "question": "Matplotlib 是什么？",
            "answer": (
                "Matplotlib 是 Python 中常用的可视化库，可绘制静态、动态和"
                "交互式图表。感谢您的提问！"
            ),
        },
        {
            "question": "如何绘制折线图？",
            "answer": (
                "可使用 plt.plot() 传入 x、y 轴数据，再调用 plt.show() 展示。"
                "感谢您的提问！"
            ),
        },
        {
            "question": "subplot 怎么用？",
            "answer": (
                "plt.subplot(行数, 列数, 序号) 可在同一画布中定位多个子图。"
                "感谢您的提问！"
            ),
        },
        {
            "question": "怎样设置图片标题？",
            "answer": (
                "可使用 plt.title() 设置标题，并通过参数调整字号和颜色。"
                "感谢您的提问！"
            ),
        },
    ]
    return SemanticSimilarityExampleSelector.from_examples(
        examples=examples,
        embeddings=get_embedding(),
        vectorstore_cls=Chroma,
        k=2,
        input_keys=["question"],
    )


def build_agent_services(
    context: SessionContext,
    token_window: int,
) -> AgentServices:
    """构建 Agent 层所需依赖；建议在用户认证成功后调用。

    此函数不缓存整个 AgentServices，因为 MCP Tool 对象绑定着用户/会话 Token；
    模型、Embedding、示例选择器及 MCP 工具发现各自通过对应工厂管理缓存。
    """
    text_llm = get_text_llm()
    embedding = get_embedding()
    tools = get_mcp_tools(context, token_window)
    tool_router = create_tool_router(tools, embedding)
    example_selector = get_example_selector()

    return AgentServices(
        text_llm=text_llm,
        embedding=embedding,
        tools=tools,
        tool_router=tool_router,
        example_selector=example_selector,
    )


__all__ = [
    "AgentServices",
    "ToolRouter",
    "_discover_mcp_tools",
    "_sync_discover_mcp_tools",
    "build_agent_services",
    "create_tool_router",
    "get_embedding",
    "get_example_selector",
    "get_mcp_tools",
    "get_text_llm",
    "run_coroutine_sync",
]
