"""用户认证、知识库权限、会话上下文与 MCP HMAC Token。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any

import streamlit as st

from config import (
    APP_USER_KB_ACCESS_JSON,
    APP_USER_TOKENS_JSON,
    IDENTIFIER_PATTERN,
    KNOWLEDGE_BASE_ID,
    MCP_REQUIRED_SCOPE,
    MCP_TOKEN_AUDIENCE,
    MCP_TOKEN_SECRET,
    MCP_TOKEN_TTL_SECONDS,
)


@dataclass(frozen=True)
class SessionContext:
    """当前用户、浏览器会话和知识库的身份上下文。"""

    user_id: str
    browser_session_id: str
    knowledge_base_id: str

    @property
    def redis_session_id(self) -> str:
        """生成按知识库、用户和浏览器会话隔离的 Redis 会话 ID。"""
        return (
            f"kb={self.knowledge_base_id}:user={self.user_id}:"
            f"session={self.browser_session_id}"
        )


def _load_json_object(raw_value: str, variable_name: str) -> dict[str, Any]:
    """解析环境变量中的 JSON 对象；格式错误时明确失败。"""
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{variable_name} 不是合法 JSON。") from exc

    if not isinstance(value, dict):
        raise RuntimeError(f"{variable_name} 必须是 JSON 对象。")
    return value


def load_user_token_hashes() -> dict[str, str]:
    """读取并验证 user_id -> SHA-256(access_token) 配置。"""
    configured = _load_json_object(
        APP_USER_TOKENS_JSON,
        "APP_USER_TOKENS_JSON",
    )
    result: dict[str, str] = {}

    for user_id, token_hash in configured.items():
        normalized_user = str(user_id).strip()
        normalized_hash = str(token_hash).strip().lower()

        if not IDENTIFIER_PATTERN.fullmatch(normalized_user):
            raise RuntimeError(f"非法用户 ID：{normalized_user!r}")
        if not re.fullmatch(r"[0-9a-f]{64}", normalized_hash):
            raise RuntimeError(
                f"用户 {normalized_user!r} 的访问令牌必须保存为 SHA-256 十六进制摘要。"
            )

        result[normalized_user] = normalized_hash

    return result


def allowed_knowledge_bases(user_id: str) -> list[str]:
    """返回当前用户可以选择的知识库列表。"""
    access_map = _load_json_object(
        APP_USER_KB_ACCESS_JSON,
        "APP_USER_KB_ACCESS_JSON",
    )

    # 与原始代码保持一致：没有配置权限映射时，默认允许默认知识库；
    # 一旦配置了权限映射，未列出的用户默认没有权限。
    configured = access_map.get(
        user_id,
        [] if access_map else [KNOWLEDGE_BASE_ID],
    )
    if not isinstance(configured, list):
        raise RuntimeError(f"用户 {user_id!r} 的知识库权限必须是 JSON 数组。")

    # 当前服务器只承载 KNOWLEDGE_BASE_ID，因此过滤掉其它知识库 ID。
    return [
        knowledge_base_id
        for knowledge_base_id in map(str, configured)
        if knowledge_base_id == KNOWLEDGE_BASE_ID
    ]


def require_authentication() -> str:
    """渲染 fail-closed 登录界面，并返回已认证用户 ID。

    本函数只处理认证相关的 Streamlit UI 和 session_state；页面布局由主入口负责。
    """
    if len(MCP_TOKEN_SECRET.encode("utf-8")) < 32:
        st.error(
            "服务未配置有效的 `MCP_TOKEN_SECRET`，"
            "已拒绝启动未鉴权客户端。请检查 API_Key_and_Tools/MCP_TOKEN_SECRET.env。"
        )
        st.stop()

    try:
        user_hashes = load_user_token_hashes()
    except RuntimeError as exc:
        st.error(str(exc))
        st.stop()

    if not user_hashes:
        st.error("未配置 `APP_USER_TOKENS_JSON`，当前没有可登录用户。")
        st.stop()

    st.session_state.setdefault(
        "browser_session_id",
        secrets.token_urlsafe(24),
    )

    authenticated_user_id = st.session_state.get("authenticated_user_id")
    authenticated_token_hash = st.session_state.get("authenticated_token_hash")

    if (
        authenticated_user_id in user_hashes
        and hmac.compare_digest(
            str(authenticated_token_hash),
            user_hashes[str(authenticated_user_id)],
        )
    ):
        return str(authenticated_user_id)

    st.title("Matplotlib 课程智能助手")
    with st.form("login_form"):
        user_id = st.text_input("用户 ID")
        access_token = st.text_input("访问令牌", type="password")
        submitted = st.form_submit_button("登录", width="stretch")

    if submitted:
        normalized_user = user_id.strip()
        # 对不存在的用户也计算摘要并走 constant-time compare，避免明显的分支差异。
        expected_hash = user_hashes.get(normalized_user, "0" * 64)
        actual_hash = hashlib.sha256(access_token.encode("utf-8")).hexdigest()

        if (
            normalized_user in user_hashes
            and hmac.compare_digest(actual_hash, expected_hash)
        ):
            st.session_state.authenticated_user_id = normalized_user
            st.session_state.authenticated_token_hash = expected_hash
            st.session_state.messages = []
            st.session_state.last_retrieved_docs = []
            st.rerun()

        st.error("用户 ID 或访问令牌错误。")

    st.stop()
    # st.stop() 会中断 Streamlit 脚本；该返回值用于满足静态类型检查。
    raise RuntimeError("Streamlit st.stop() 未中断脚本执行。")


def current_session_context(user_id: str) -> SessionContext:
    """结合已认证用户、当前浏览器会话和选定知识库构造 SessionContext。"""
    allowed = allowed_knowledge_bases(user_id)
    if not allowed:
        raise PermissionError("当前用户没有任何知识库访问权限。")

    selected = st.session_state.get("knowledge_base_id", allowed[0])
    if selected not in allowed:
        selected = allowed[0]
        st.session_state.knowledge_base_id = selected

    browser_session_id = st.session_state.get("browser_session_id")
    if not browser_session_id:
        browser_session_id = secrets.token_urlsafe(24)
        st.session_state.browser_session_id = browser_session_id

    return SessionContext(
        user_id=user_id,
        browser_session_id=str(browser_session_id),
        knowledge_base_id=str(selected),
    )


def _base64url(value: bytes) -> str:
    """无填充的 URL-safe Base64 编码。"""
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_mcp_context_token(
    context: SessionContext,
    token_window: int,
) -> str:
    """创建带用户、会话、知识库和 scope 声明的短期 HMAC Token。

    token_window 通常传入 int(time.time()) // MCP_TOKEN_TTL_SECONDS，
    以便同一个时间窗口内复用相同的令牌时间边界。
    """
    secret_bytes = MCP_TOKEN_SECRET.encode("utf-8")
    if len(secret_bytes) < 32:
        raise RuntimeError("MCP_TOKEN_SECRET 未配置或少于 32 字节，无法签发 MCP Token。")

    expires_at = (token_window + 2) * MCP_TOKEN_TTL_SECONDS
    payload = {
        "sub": context.user_id,
        "sid": context.browser_session_id,
        "kb": context.knowledge_base_id,
        "aud": MCP_TOKEN_AUDIENCE,
        "scopes": [MCP_REQUIRED_SCOPE],
        "iat": token_window * MCP_TOKEN_TTL_SECONDS,
        "exp": expires_at,
    }

    payload_part = _base64url(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    signature = hmac.new(
        secret_bytes,
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()

    return f"{payload_part}.{_base64url(signature)}"


__all__ = [
    "SessionContext",
    "allowed_knowledge_bases",
    "create_mcp_context_token",
    "current_session_context",
    "load_user_token_hashes",
    "require_authentication",
]
