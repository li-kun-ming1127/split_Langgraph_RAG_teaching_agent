"""Matplotlib 教学助手的 Streamlit 主入口。

本文件只负责 UI 与应用流程编排。模型、MCP、LangGraph、Redis、认证等
逻辑分别放在 config.py、auth.py、services.py、memory.py、agent.py、utils.py。

注意：这是拆分后的 UI 入口文件；需要配套创建上述模块并导出本文引用的函数，
才能直接运行。当前阶段先保持单 Agent 行为不变。
"""

from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from agent import get_rag_chain_with_memory
from auth import allowed_knowledge_bases, current_session_context, require_authentication
from config import MCP_SERVER_URL
from memory import clear_session_memory, compact_redis_history, refresh_session_ttl
from services import run_coroutine_sync
from utils import AgentMonitorHandler, format_token_usage


LOGGER = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Streamlit 页面初始化与会话状态
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Matplotlib 教学助手", layout="wide")


def initialize_session_state(session_context) -> None:
    """初始化仅用于前端渲染的状态，并在用户/会话/知识库改变时清理旧 UI 状态。"""
    st.session_state.setdefault("role_for_prompt", "beginner")
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("last_retrieved_docs", [])
    st.session_state.setdefault("last_token_usage", {})

    context_key = session_context.redis_session_id
    if st.session_state.get("active_context_key") != context_key:
        st.session_state.messages = []
        st.session_state.last_retrieved_docs = []
        st.session_state.last_token_usage = {}
        st.session_state.active_context_key = context_key


def render_sidebar(session_context) -> None:
    """渲染侧边栏：会话管理、知识库、回答难度、Token 与检索来源。"""
    with st.sidebar:
        st.subheader("控制面板")
        st.caption(f"用户：{session_context.user_id}")

        allowed_kbs = allowed_knowledge_bases(session_context.user_id)
        if allowed_kbs:
            st.selectbox(
                "知识库",
                options=allowed_kbs,
                key="knowledge_base_id",
            )
        else:
            st.error("当前用户没有可访问的知识库。")
            st.stop()

        if st.button("新建会话", width="stretch"):
            # 通过新 browser_session_id 创建隔离的新 Redis 会话。
            import secrets

            st.session_state.browser_session_id = secrets.token_urlsafe(24)
            st.session_state.messages = []
            st.session_state.last_retrieved_docs = []
            st.session_state.last_token_usage = {}
            st.session_state.pop("active_context_key", None)
            st.rerun()

        if st.button("清空对话历史", width="stretch"):
            st.session_state.messages = []
            st.session_state.last_retrieved_docs = []
            st.session_state.last_token_usage = {}
            clear_session_memory(session_context.redis_session_id)
            st.rerun()

        if st.button("退出登录", width="stretch"):
            st.session_state.pop("authenticated_user_id", None)
            st.session_state.pop("authenticated_token_hash", None)
            st.session_state.pop("active_context_key", None)
            import secrets

            st.session_state.browser_session_id = secrets.token_urlsafe(24)
            st.session_state.messages = []
            st.session_state.last_retrieved_docs = []
            st.session_state.last_token_usage = {}
            st.rerun()

        st.subheader("角色设定")
        role_label = st.radio(
            "请选择回答难度",
            options=["新手", "专家", "通用"],
            index=0,
            key="user_role",
        )
        st.session_state.role_for_prompt = {
            "新手": "beginner",
            "专家": "expert",
            "通用": "user",
        }[role_label]

        st.subheader("本轮模型用量")
        st.caption(format_token_usage(st.session_state.last_token_usage))

        st.subheader("最近检索的文档")
        render_retrieved_documents(st.session_state.last_retrieved_docs)

        st.subheader("对话历史")
        render_history_preview(st.session_state.messages)


def render_retrieved_documents(documents: list) -> None:
    """显示本轮检索到的来源文档。"""
    if not documents:
        st.caption("暂无检索结果")
        return

    for index, document in enumerate(documents, start=1):
        metadata = document.metadata or {}
        source_name = Path(str(metadata.get("source", "未知来源"))).name
        page_number = int(metadata.get("page", 0)) + 1
        with st.expander(f"片段 {index}（{source_name} 第 {page_number} 页）"):
            content = document.page_content
            doc_type = metadata.get("type", "text")

            if doc_type == "image":
                asset_path = metadata.get("asset_path")
                if asset_path and Path(str(asset_path)).is_file():
                    st.image(
                        str(asset_path),
                        caption=f"{source_name} 第 {page_number} 页",
                    )
                preview = content[:500] + "..." if len(content) > 500 else content
            else:
                preview = content[:300] + "..." if len(content) > 300 else content

            st.write(preview)


def render_history_preview(messages: list[tuple[str, str]]) -> None:
    """显示简短的历史问题预览。"""
    if not messages:
        st.caption("暂无历史")
        return

    for user_message, _ in messages:
        preview = user_message[:50] + "..." if len(user_message) > 50 else user_message
        st.caption(f"用户：{preview}")


# -----------------------------------------------------------------------------
# 聊天展示与 Agent 调用
# -----------------------------------------------------------------------------
def render_chat_history(messages: list[tuple[str, str]]) -> None:
    """渲染当前 Streamlit 会话中的聊天记录。"""
    for user_message, assistant_message in messages:
        with st.chat_message("user"):
            st.write(user_message)
        with st.chat_message("assistant"):
            st.write(assistant_message)


def process_user_prompt(prompt: str, session_context) -> None:
    """调用 LangGraph Agent，展示答案并更新 Token、来源文档和 Redis 记忆。"""
    st.chat_message("user").write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("思考中..."):
            monitor = AgentMonitorHandler()
            try:
                # agent.py 提供已经组装好的 RunnableWithMessageHistory。
                rag_chain = get_rag_chain_with_memory(session_context)

                # MCP 工具是异步工具，因此整张链路使用 ainvoke。
                result = run_coroutine_sync(
                    rag_chain.ainvoke(
                        {"question": prompt},
                        config={
                            "configurable": {
                                "session_id": session_context.redis_session_id,
                                "user_id": session_context.user_id,
                                "knowledge_base_id": session_context.knowledge_base_id,
                                "user_role": st.session_state.role_for_prompt,
                            },
                            "callbacks": [monitor],
                        },
                    )
                )

                answer = result["answer"]
                st.session_state.last_retrieved_docs = result.get("retrieved_docs", [])

            except Exception as exc:
                LOGGER.exception("处理 Streamlit 请求失败，question=%r", prompt)
                answer = (
                    "处理请求时发生错误。请检查 MCP 服务、Redis 和模型配置后重试。\n\n"
                    f"错误详情：{exc}\n\nMCP 服务地址：`{MCP_SERVER_URL}`"
                )
                st.session_state.last_retrieved_docs = []

            st.session_state.last_token_usage = monitor.token_usage()
            LOGGER.info(
                "本轮模型 token 汇总：session=%s usage=%s",
                session_context.redis_session_id,
                st.session_state.last_token_usage,
            )
            st.write(answer)

    st.session_state.messages.append((prompt, answer))

    try:
        compact_redis_history(session_context.redis_session_id)
        refresh_session_ttl(session_context.redis_session_id)
    except Exception:
        LOGGER.exception(
            "对话已完成，但 Redis 历史压缩或 TTL 刷新失败：session=%s",
            session_context.redis_session_id,
        )
        st.warning("对话已完成，但 Redis 历史压缩或 TTL 刷新失败；详情请查看日志。")


# -----------------------------------------------------------------------------
# 应用入口
# -----------------------------------------------------------------------------
def main() -> None:
    authenticated_user_id = require_authentication()

    try:
        session_context = current_session_context(authenticated_user_id)
    except (RuntimeError, PermissionError) as exc:
        st.error(str(exc))
        st.stop()
        return

    initialize_session_state(session_context)
    st.title("Matplotlib 课程智能助手")

    render_sidebar(session_context)
    render_chat_history(st.session_state.messages)

    if prompt := st.chat_input("请输入你的问题...", disabled=False):
        process_user_prompt(prompt, session_context)


if __name__ == "__main__":
    main()
