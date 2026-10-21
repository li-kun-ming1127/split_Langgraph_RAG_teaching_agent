"""Redis 会话记忆、历史摘要、上下文预算与工具结果缓存。

本模块从 config.py 读取配置，不负责 Streamlit 页面、Agent 节点或 MCP 连接初始化。
原始单 Agent 版本中的历史管理和缓存策略在此集中维护。
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from typing import Any, Sequence

import redis
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from config import (
    CONTEXT_INPUT_BUDGET_TOKENS,
    HISTORY_TARGET_TOKENS,
    MAX_HISTORY_MESSAGES,
    MAX_TOOL_MESSAGE_TOKENS,
    MIN_RECENT_TURNS,
    REDIS_KEY_PREFIX,
    REDIS_TTL_SECONDS,
    REDIS_URL,
    SAFETY_MARGIN_TOKENS,
    SUMMARY_INPUT_TOKENS,
    SUMMARY_OUTPUT_TOKENS,
    TOKEN_ESTIMATE_CHARS_PER_TOKEN,
)

LOGGER = logging.getLogger(__name__)

# Redis.from_url 本身不会立即建立网络连接；实际操作发生在读写时。
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)


# -----------------------------------------------------------------------------
# Redis 会话历史、摘要存储与 TTL
# -----------------------------------------------------------------------------
def get_session_history(session_id: str) -> RedisChatMessageHistory:
    """返回指定会话的 Redis 消息历史。"""
    return RedisChatMessageHistory(
        session_id=session_id,
        url=REDIS_URL,
        key_prefix=f"{REDIS_KEY_PREFIX}:history:",
        ttl=REDIS_TTL_SECONDS,
    )


def get_cached_summary(session_id: str) -> tuple[str | None, int]:
    """读取指定会话的摘要及已压缩消息数。"""
    summary = redis_client.get(f"{REDIS_KEY_PREFIX}:summary:{session_id}")
    compacted_count = redis_client.get(
        f"{REDIS_KEY_PREFIX}:summary_until:{session_id}"
    )
    return summary, int(compacted_count or 0)


def set_cached_summary(
    session_id: str,
    summary: str,
    compacted_count: int,
) -> None:
    """将会话摘要和压缩进度写入 Redis，并设置 TTL。"""
    with redis_client.pipeline() as pipeline:
        pipeline.setex(
            f"{REDIS_KEY_PREFIX}:summary:{session_id}",
            REDIS_TTL_SECONDS,
            summary,
        )
        pipeline.setex(
            f"{REDIS_KEY_PREFIX}:summary_until:{session_id}",
            REDIS_TTL_SECONDS,
            str(compacted_count),
        )
        pipeline.execute()


def refresh_session_ttl(session_id: str) -> None:
    """刷新指定会话的消息历史、摘要和摘要进度 TTL。"""
    keys = (
        f"{REDIS_KEY_PREFIX}:history:{session_id}",
        f"{REDIS_KEY_PREFIX}:summary:{session_id}",
        f"{REDIS_KEY_PREFIX}:summary_until:{session_id}",
    )
    with redis_client.pipeline() as pipeline:
        for key in keys:
            pipeline.expire(key, REDIS_TTL_SECONDS)
        pipeline.execute()


def clear_session_memory(session_id: str) -> None:
    """清除指定会话的消息历史、摘要及摘要进度。"""
    history = get_session_history(session_id)
    history.clear()
    redis_client.delete(
        f"{REDIS_KEY_PREFIX}:summary:{session_id}",
        f"{REDIS_KEY_PREFIX}:summary_until:{session_id}",
    )


# -----------------------------------------------------------------------------
# Token 估算、消息轮次切分与历史摘要
# -----------------------------------------------------------------------------
def truncate_text(text: str, max_tokens: int) -> str:
    """按近似 Token 预算截断文本，同时尽量保留开头和结尾。"""
    max_chars = max(256, int(max_tokens * TOKEN_ESTIMATE_CHARS_PER_TOKEN))
    if len(text) <= max_chars:
        return text

    head = max_chars * 2 // 3
    tail = max_chars - head
    return f"{text[:head]}\n...[内容已按 token 预算截断]...\n{text[-tail:]}"


def estimate_message_tokens(
    messages: Sequence[Any],
    include_tools: bool = False,
    tools: Sequence[Any] | None = None,
) -> int:
    """估算消息 Token 数；需要估算工具定义时由调用者传入 tools。"""
    return count_tokens_approximately(
        list(messages),
        chars_per_token=TOKEN_ESTIMATE_CHARS_PER_TOKEN,
        tools=list(tools) if include_tools and tools is not None else None,
    )


def split_into_turns(messages: Sequence[Any]) -> list[list[Any]]:
    """将一条 HumanMessage 及后续 AI/Tool 消息归为完整对话轮次。"""
    turns: list[list[Any]] = []
    current: list[Any] = []

    for message in messages:
        if isinstance(message, SystemMessage):
            continue
        if isinstance(message, HumanMessage) and current:
            turns.append(current)
            current = []
        current.append(message)

    if current:
        turns.append(current)
    return turns


def flatten_turns(turns: Sequence[Sequence[Any]]) -> list[Any]:
    """将轮次列表展开为消息列表。"""
    return [message for turn in turns for message in turn]


def truncate_oversized_tool_messages(
    turns: Sequence[Sequence[Any]],
    max_tool_message_tokens: int = MAX_TOOL_MESSAGE_TOKENS,
) -> list[list[Any]]:
    """截断过大的 ToolMessage，但保留原有工具调用/返回消息关系。"""
    bounded_turns: list[list[Any]] = []

    for turn in turns:
        bounded_turn: list[Any] = []
        for message in turn:
            if (
                isinstance(message, ToolMessage)
                and estimate_message_tokens([message]) > max_tool_message_tokens
            ):
                bounded_content = truncate_text(
                    str(message.content), max_tool_message_tokens
                )
                message = message.model_copy(update={"content": bounded_content})
            bounded_turn.append(message)
        bounded_turns.append(bounded_turn)

    return bounded_turns


def format_messages_for_summary(messages: Sequence[Any]) -> str:
    """把对话消息转换为摘要输入，并限制工具结果长度。"""
    formatted: list[str] = []

    for message in messages:
        if isinstance(message, HumanMessage):
            formatted.append(f"用户：{message.content}")
        elif isinstance(message, AIMessage):
            if message.content:
                formatted.append(f"助手：{message.content}")
            if message.tool_calls:
                calls = []
                for call in message.tool_calls:
                    args = call.get("args", {}) if isinstance(call, dict) else {}
                    calls.append(
                        {
                            "tool": call.get("name", "unknown")
                            if isinstance(call, dict)
                            else "unknown",
                            "query": str(args.get("query", ""))[:300]
                            if isinstance(args, dict)
                            else "",
                        }
                    )
                formatted.append(
                    "[助手工具调用摘要："
                    + json.dumps(calls, ensure_ascii=False)
                    + "]"
                )
        elif isinstance(message, ToolMessage):
            tool_name = getattr(message, "name", None) or "tool"
            content = truncate_text(str(message.content), MAX_TOOL_MESSAGE_TOKENS)
            formatted.append(f"工具[{tool_name}]：{content}")

    return "\n".join(formatted)


@lru_cache(maxsize=1)
def _get_summary_chain():
    """延迟创建摘要链，避免导入 memory.py 时提前初始化模型。"""
    # 延迟导入以避免模块导入阶段产生不必要的模型初始化或循环依赖。
    from services import get_text_llm

    summary_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "请用中文简洁地总结以下对话要点，突出技术问题与答案。"),
            ("human", "{chat_history}"),
        ]
    )
    return (
        summary_prompt
        | get_text_llm().bind(max_tokens=SUMMARY_OUTPUT_TOKENS)
        | StrOutputParser()
    )


def summarize_messages(
    messages: Sequence[Any],
    existing_summary: str | None = None,
) -> str:
    """将待压缩消息合并进已有摘要，控制摘要输入和输出预算。"""
    new_history = format_messages_for_summary(messages)
    if not new_history.strip():
        return existing_summary or "暂无历史"

    chat_history = new_history
    if existing_summary:
        chat_history = (
            f"已有摘要：\n{existing_summary}\n\n新增对话：\n{new_history}"
        )
    chat_history = truncate_text(chat_history, SUMMARY_INPUT_TOKENS)
    return _get_summary_chain().invoke({"chat_history": chat_history})


def prepare_effective_messages(
    messages: Sequence[Any],
    session_id: str,
) -> list[Any]:
    """将 Redis 中持久化的摘要作为系统消息放在近期对话前。"""
    cached_summary, _ = get_cached_summary(session_id)
    if not cached_summary:
        return list(messages)

    return [
        SystemMessage(content=f"历史对话摘要：\n{cached_summary}"),
        *messages,
    ]


def compact_redis_history(session_id: str) -> None:
    """按 Token/消息数量预算压缩旧轮次，保留最近的完整轮次。"""
    history = get_session_history(session_id)
    messages = history.messages
    turns = split_into_turns(messages)
    if not turns:
        return

    evicted_turns: list[list[Any]] = []
    while len(turns) > MIN_RECENT_TURNS:
        candidate = flatten_turns(turns)
        over_tokens = estimate_message_tokens(candidate) > HISTORY_TARGET_TOKENS
        over_count = len(candidate) > MAX_HISTORY_MESSAGES
        if not over_tokens and not over_count:
            break
        evicted_turns.append(turns.pop(0))

    if not evicted_turns:
        return

    old_messages = flatten_turns(evicted_turns)
    recent_messages = flatten_turns(turns)
    cached_summary, compacted_count = get_cached_summary(session_id)
    new_summary = summarize_messages(old_messages, cached_summary)

    set_cached_summary(
        session_id,
        new_summary,
        compacted_count + len(old_messages),
    )

    history.clear()
    history.add_messages(recent_messages)


def build_model_context(
    dynamic_system_prompt: str,
    messages: Sequence[Any],
    session_id: str,
    tools: Sequence[Any] | None = None,
) -> list[Any]:
    """构建满足上下文预算的消息列表，优先保留最近的完整对话轮次。

    tools 用于估算本次模型调用所需的工具 Schema Token；因为 tools 在 services.py
    中按当前会话创建，所以通过参数传入，不依赖全局工具变量。
    """
    historical_system = [
        message for message in messages if isinstance(message, SystemMessage)
    ]
    turns = split_into_turns(messages)
    if not turns:
        return [SystemMessage(content=dynamic_system_prompt), *historical_system]

    def candidate_messages() -> list[Any]:
        return [
            SystemMessage(content=dynamic_system_prompt),
            *historical_system,
            *flatten_turns(turns),
        ]

    evicted_turns: list[list[Any]] = []
    while len(turns) > MIN_RECENT_TURNS and estimate_message_tokens(
        candidate_messages(), include_tools=True, tools=tools
    ) > CONTEXT_INPUT_BUDGET_TOKENS:
        evicted_turns.append(turns.pop(0))

    # 若仍超预算，硬预算优先；尽量保留当前轮的完整消息。
    while len(turns) > 1 and estimate_message_tokens(
        candidate_messages(), include_tools=True, tools=tools
    ) > CONTEXT_INPUT_BUDGET_TOKENS:
        evicted_turns.append(turns.pop(0))

    if evicted_turns:
        cached_summary, _ = get_cached_summary(session_id)
        new_summary = summarize_messages(
            flatten_turns(evicted_turns), cached_summary
        )
        historical_system = [SystemMessage(content=f"历史对话摘要：\n{new_summary}")]

    turns = truncate_oversized_tool_messages(turns)
    context = candidate_messages()
    estimated_tokens = estimate_message_tokens(
        context, include_tools=True, tools=tools
    )
    if estimated_tokens > CONTEXT_INPUT_BUDGET_TOKENS:
        raise RuntimeError(
            "当前 system、工具定义和最近完整轮次超过上下文预算："
            f"estimated={estimated_tokens}, budget={CONTEXT_INPUT_BUDGET_TOKENS}。"
            "请降低单次工具结果、RAG top_k 或 MAX_TOOL_MESSAGE_TOKENS。"
        )

    LOGGER.info(
        "上下文预算：estimated=%d budget=%d turns=%d safety_margin=%d",
        estimated_tokens,
        CONTEXT_INPUT_BUDGET_TOKENS,
        len(turns),
        SAFETY_MARGIN_TOKENS,
    )
    return context


# -----------------------------------------------------------------------------
# MCP 搜索工具结果缓存
# -----------------------------------------------------------------------------
def _tool_cache_key(session_id: str, tool_name: str, query: str) -> str:
    """根据会话、工具名和查询生成隔离的 Redis 缓存键。"""
    digest = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()
    return (
        f"{REDIS_KEY_PREFIX}:tool-cache:{session_id}:{tool_name}:{digest}"
    )


def get_cached_tool_result(
    session_id: str,
    tool_name: str,
    query: str,
) -> str | None:
    """读取可缓存的工具结果；目前只缓存知识检索工具。"""
    if tool_name != "search_matplotlib_knowledge" or not query.strip():
        return None

    try:
        return redis_client.get(_tool_cache_key(session_id, tool_name, query))
    except Exception:
        LOGGER.warning("读取工具结果缓存失败", exc_info=True)
        return None


def serialize_tool_content(content: Any) -> str:
    """将工具返回值转换为可以写入 Redis 的字符串。"""
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False)
    return str(content)


def set_cached_tool_result(
    session_id: str,
    tool_name: str,
    query: str,
    result: str,
) -> None:
    """缓存知识检索结果；缓存故障不应阻断主对话流程。"""
    if (
        tool_name != "search_matplotlib_knowledge"
        or not query.strip()
        or not result
    ):
        return

    try:
        redis_client.setex(
            _tool_cache_key(session_id, tool_name, query),
            REDIS_TTL_SECONDS,
            result,
        )
    except Exception:
        LOGGER.warning("写入工具结果缓存失败", exc_info=True)


__all__ = [
    "build_model_context",
    "clear_session_memory",
    "compact_redis_history",
    "estimate_message_tokens",
    "flatten_turns",
    "format_messages_for_summary",
    "get_cached_summary",
    "get_cached_tool_result",
    "get_session_history",
    "prepare_effective_messages",
    "refresh_session_ttl",
    "redis_client",
    "serialize_tool_content",
    "set_cached_summary",
    "set_cached_tool_result",
    "split_into_turns",
    "summarize_messages",
    "truncate_oversized_tool_messages",
    "truncate_text",
]
