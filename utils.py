"""
LangGraph RAG Teaching Agent 通用工具模块。

本文件只负责与具体业务 Agent 解耦的通用辅助功能：

1. Token 使用量统计
2. LangChain 模型调用监控回调
3. MCP Tool 返回结果安全解析
4. 从 ToolMessage 中提取检索文档
5. Token 用量格式化

注意：
- 不负责 Streamlit UI
- 不负责用户认证
- 不负责 Redis
- 不负责 MCP Client 初始化
- 不负责 Agent / LangGraph 构建
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import ToolMessage


LOGGER = logging.getLogger(__name__)


# =============================================================================
# Token 使用量统计
# =============================================================================

def _safe_int(value: Any) -> int:
    """将可能为空、字符串或非法值的对象安全转换为 int。"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _extract_usage_from_response(response: Any) -> dict[str, int]:
    """
    从 LangChain / OpenAI-compatible 模型响应中提取 Token 使用量。

    兼容：
    - usage_metadata
    - response_metadata.token_usage
    - response_metadata.usage
    - prompt_tokens / completion_tokens
    - input_tokens / output_tokens
    """
    usage: dict[str, Any] = {}

    # -------------------------------------------------------------------------
    # LangChain AIMessage.usage_metadata
    # -------------------------------------------------------------------------
    usage_metadata = getattr(response, "usage_metadata", None)

    if isinstance(usage_metadata, dict):
        usage.update(usage_metadata)

    # -------------------------------------------------------------------------
    # OpenAI-compatible response_metadata
    # -------------------------------------------------------------------------
    response_metadata = getattr(response, "response_metadata", None)

    if isinstance(response_metadata, dict):
        token_usage = response_metadata.get("token_usage")

        if isinstance(token_usage, dict):
            usage.update(token_usage)

        metadata_usage = response_metadata.get("usage")

        if isinstance(metadata_usage, dict):
            usage.update(metadata_usage)

    # -------------------------------------------------------------------------
    # 统一字段名称
    # -------------------------------------------------------------------------
    input_tokens = _safe_int(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("prompt_token_count")
    )

    output_tokens = _safe_int(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("completion_token_count")
    )

    total_tokens = _safe_int(
        usage.get("total_tokens")
        or usage.get("total_token_count")
    )

    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


class AgentMonitorHandler(BaseCallbackHandler):
    """
    LangChain/LangGraph Agent Token 使用量监控回调。

    主要作用：
    - 统计一次 Agent 执行过程中所有 LLM 调用的 Token
    - 兼容 DeepSeek/OpenAI-compatible usage 字段
    - 不修改 Agent 的执行逻辑
    - 不参与工具选择和路由
    """

    def __init__(self) -> None:
        super().__init__()

        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0

        self.llm_calls = 0

    def _add_usage(self, usage: dict[str, int]) -> None:
        """累计一次模型调用的 Token 使用量。"""
        self.input_tokens += _safe_int(usage.get("input_tokens"))
        self.output_tokens += _safe_int(usage.get("output_tokens"))

        total = _safe_int(usage.get("total_tokens"))

        if total <= 0:
            total = (
                _safe_int(usage.get("input_tokens"))
                + _safe_int(usage.get("output_tokens"))
            )

        self.total_tokens += total

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """
        捕获普通 LLM 调用结束事件。

        某些 LangChain 模型可能通过 on_chat_model_end 进入，
        因此这里主要作为兼容路径。
        """
        self.llm_calls += 1

        try:
            generations = getattr(response, "generations", None)

            if generations:
                for generation_group in generations:
                    for generation in generation_group:
                        message = getattr(generation, "message", None)

                        if message is not None:
                            usage = _extract_usage_from_response(message)
                            self._add_usage(usage)

        except Exception:
            LOGGER.exception("解析 LLM Token 使用量失败。")

    def on_chat_model_end(
        self,
        response: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """捕获 ChatModel 调用结束事件。"""
        try:
            usage = _extract_usage_from_response(response)
            self._add_usage(usage)

        except Exception:
            LOGGER.exception("解析 ChatModel Token 使用量失败。")

    def token_usage(self) -> dict[str, int]:
        """返回当前 Agent 执行累计的 Token 使用量。"""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
        }


def format_token_usage(usage: dict[str, Any] | None) -> str:
    """
    将 Token 使用量格式化为适合 Streamlit 侧边栏显示的文本。
    """
    if not usage:
        return "暂无 Token 使用量"

    input_tokens = _safe_int(usage.get("input_tokens"))
    output_tokens = _safe_int(usage.get("output_tokens"))
    total_tokens = _safe_int(usage.get("total_tokens"))
    llm_calls = _safe_int(usage.get("llm_calls"))

    return (
        f"调用 {llm_calls} 次 · "
        f"输入 {input_tokens:,} · "
        f"输出 {output_tokens:,} · "
        f"总计 {total_tokens:,}"
    )


# =============================================================================
# MCP Tool 结果解析
# =============================================================================

def safe_parse_tool_result(content: Any) -> Any:
    """
    安全解析 MCP / LangChain Tool 返回结果。

    MCP Tool 返回值可能是：
    - dict
    - list
    - JSON 字符串
    - 普通字符串
    - 带 text 字段的对象
    - 空值

    解析失败时不抛出 JSONDecodeError，而是返回原始内容。
    """

    if content is None:
        return None

    if isinstance(content, (dict, list, tuple)):
        return content

    # -------------------------------------------------------------------------
    # LangChain 某些工具返回的 content 可能是对象
    # -------------------------------------------------------------------------
    if hasattr(content, "text"):
        text_content = getattr(content, "text", None)

        if isinstance(text_content, str):
            content = text_content

    if not isinstance(content, str):
        return content

    cleaned = content.strip()

    if not cleaned:
        return ""

    # -------------------------------------------------------------------------
    # 尝试直接解析 JSON
    # -------------------------------------------------------------------------
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # -------------------------------------------------------------------------
    # 有些模型/工具可能返回 ```json ... ```
    # -------------------------------------------------------------------------
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned_json = "\n".join(lines).strip()

        try:
            return json.loads(cleaned_json)
        except json.JSONDecodeError:
            pass

    # -------------------------------------------------------------------------
    # JSON 解析失败，保留原始字符串
    # -------------------------------------------------------------------------
    return content


# =============================================================================
# MCP 检索结果 → LangChain Document
# =============================================================================

def _document_from_result(result: Any) -> Document | None:
    """
    将单个 MCP RAG result 转换为 LangChain Document。
    """

    if not isinstance(result, dict):
        return None

    content = result.get("content")

    if content is None:
        content = result.get("page_content")

    if content is None:
        return None

    metadata = result.get("metadata", {})

    if not isinstance(metadata, dict):
        metadata = {}

    # 保留 MCP 返回的 summary
    if result.get("summary") and "summary" not in metadata:
        metadata["summary"] = result["summary"]

    # 保留 RAG Fusion 信息
    fusion = result.get("fusion")

    if isinstance(fusion, dict):
        metadata.setdefault(
            "fusion_score",
            fusion.get("score"),
        )
        metadata.setdefault(
            "fusion_rank",
            fusion.get("rank"),
        )
        metadata.setdefault(
            "matched_queries",
            fusion.get("matched_queries"),
        )
        metadata.setdefault(
            "query_ranks",
            fusion.get("query_ranks"),
        )

    return Document(
        page_content=str(content),
        metadata=metadata,
    )


def documents_from_tool_messages(
    messages: list[Any],
) -> list[Document]:
    """
    从 LangGraph / LangChain ToolMessage 中提取 MCP RAG 检索结果。

    预期 MCP search_matplotlib_knowledge 返回：

    {
        "knowledge_base_id": "...",
        "queries": [...],
        "results": [
            {
                "type": "...",
                "content": "...",
                "summary": "...",
                "metadata": {...},
                "fusion": {...}
            }
        ]
    }

    返回：
        list[Document]

    用于：
        - Streamlit 侧边栏展示最近检索文档
        - Agent 最终结果中的 retrieved_docs
        - 后续前端引用来源
    """

    documents: list[Document] = []

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue

        content = getattr(message, "content", None)

        parsed = safe_parse_tool_result(content)

        # ---------------------------------------------------------------------
        # MCP 返回标准结构
        # ---------------------------------------------------------------------
        if isinstance(parsed, dict):
            results = parsed.get("results")

            if isinstance(results, list):
                for result in results:
                    document = _document_from_result(result)

                    if document is not None:
                        documents.append(document)

        # ---------------------------------------------------------------------
        # 某些工具可能直接返回 result list
        # ---------------------------------------------------------------------
        elif isinstance(parsed, list):
            for result in parsed:
                document = _document_from_result(result)

                if document is not None:
                    documents.append(document)

    return documents


# =============================================================================
# 消息 / 文档辅助函数
# =============================================================================

def get_message_content(message: Any) -> str:
    """
    安全获取 LangChain Message 的文本内容。

    兼容：
    - str
    - list content block
    - 普通对象
    """

    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []

        for block in content:
            if isinstance(block, str):
                text_parts.append(block)

            elif isinstance(block, dict):
                text_value = block.get("text")

                if isinstance(text_value, str):
                    text_parts.append(text_value)

        return "\n".join(text_parts)

    return str(content)


def deduplicate_documents(
    documents: list[Document],
) -> list[Document]:
    """
    按 doc_id / source + page + content 对检索结果去重。
    """

    unique_documents: list[Document] = []
    seen: set[str] = set()

    for document in documents:
        metadata = document.metadata or {}

        doc_id = metadata.get("doc_id")

        if doc_id:
            key = f"doc_id:{doc_id}"
        else:
            source = metadata.get("source", "")
            page = metadata.get("page", "")
            content = document.page_content

            key = (
                f"{source}|"
                f"{page}|"
                f"{content}"
            )

        if key in seen:
            continue

        seen.add(key)
        unique_documents.append(document)

    return unique_documents


def truncate_text(
    text: str,
    max_length: int,
) -> str:
    """
    安全截断文本，用于 UI 预览和日志。
    """

    if len(text) <= max_length:
        return text

    return text[:max_length] + "..."


# =============================================================================
# 导出接口
# =============================================================================

__all__ = [
    "AgentMonitorHandler",
    "safe_parse_tool_result",
    "documents_from_tool_messages",
    "format_token_usage",
    "get_message_content",
    "deduplicate_documents",
    "truncate_text",
]