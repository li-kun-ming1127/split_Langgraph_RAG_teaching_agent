"""
Matplotlib 教学助手的 LangGraph Agent 核心。

本模块负责原始 ReAct_agent_loop_with_toolnode.py 中的：

1. AgentState
2. Agent Prompt
3. Agent 节点
4. MCP 工具选择
5. ToolNode / 工具执行
6. 条件路由
7. LangGraph 构建与编译
8. input_adapter / output_adapter
9. RunnableWithMessageHistory
10. 对外提供 get_rag_chain_with_memory()

当前阶段：
    保持原来的单 Agent 行为不变。

后续阶段：
    在本模块稳定以后，再将单 Agent 升级为
    Supervisor + 多个专业 ReAct 子 Agent。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Annotated, Any, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from config import (
    MAX_AGENT_STEPS,
    MCP_REQUIRED_SCOPE,
    MCP_TOKEN_TTL_SECONDS,
)
from memory import (
    build_model_context,
    get_cached_tool_result,
    get_session_history,
    prepare_effective_messages,
    serialize_tool_content,
    set_cached_tool_result,
)
from services import (
    get_mcp_tools,
    get_text_llm,
    run_coroutine_sync,
    ToolRouter,
)

LOGGER = logging.getLogger(__name__)


# =============================================================================
# 1. Agent State
# =============================================================================

class AgentState(TypedDict, total=False):
    """
    原单 Agent 的 LangGraph 状态。

    messages:
        当前 Agent 的完整消息流。

    turn_start:
        当前用户问题在消息列表中的起始位置。

    step_count:
        当前 ReAct 循环已经执行的步数。

    max_steps:
        本轮最大 Agent 步数，防止无限循环。

    retrieved_docs:
        MCP 检索得到、用于 UI 展示的文档信息。

    selected_tool_names:
        当前 Agent 实际允许调用的工具名称。
    """

    messages: Annotated[list[BaseMessage], add_messages]
    turn_start: int
    step_count: int
    max_steps: int
    retrieved_docs: list[Any]
    selected_tool_names: list[str]


# =============================================================================
# 2. Prompt
# =============================================================================

SYSTEM_PROMPT = """
你是一个专业的 Matplotlib 中文课程教学助手。

你的主要任务是：
1. 根据用户的问题进行准确回答。
2. 涉及 Matplotlib 课程知识时，优先使用提供的课程知识库工具进行检索。
3. 回答必须以检索到的课程资料为重要依据，不得凭空编造课程内容。
4. 如果用户的问题涉及代码，应尽可能给出清晰、可运行的 Python / Matplotlib 示例。
5. 对函数、参数、绘图原理和代码进行解释时，要根据用户的学习程度调整表达方式。
6. 如果知识库没有找到足够的信息，应明确说明，而不是假装资料中存在相关内容。
7. 不要向用户暴露内部 Agent、ToolNode、MCP、Redis、Prompt 等实现细节。

回答风格：
- 新手：解释详细、循序渐进。
- 专家：突出原理、参数、设计思想和技术细节。
- 通用：在准确性的基础上保持适中的解释深度。

你可以调用已经提供给你的工具完成知识检索。
只有在确实需要时才调用工具。
"""


def build_system_prompt(user_role: str = "user") -> str:
    """根据用户角色生成最终 System Prompt。"""

    role_instruction = {
        "beginner": """
当前用户为 Matplotlib 初学者。
请尽量使用通俗语言解释，并按照“概念 → 原理 → 代码 → 运行效果/注意事项”的顺序教学。
""",
        "expert": """
当前用户具有较强的 Python / Matplotlib 基础。
可以减少基础解释，重点说明 API、参数机制、绘图对象关系、实现原理和工程实践。
""",
        "user": """
当前用户学习程度未知。
请保持适中的技术深度，在保证准确性的情况下兼顾解释性。
""",
    }.get(user_role, """
当前用户学习程度未知。
请保持适中的技术深度。
""")

    return SYSTEM_PROMPT + "\n" + role_instruction


# =============================================================================
# 3. Agent 工具选择
# =============================================================================

def select_agent_tools(
    all_tools: list[Any],
    selected_tool_names: list[str] | None = None,
) -> list[Any]:
    """
    从 MCP 发现的全部工具中筛选当前 Agent 可以使用的工具。

    当前单 Agent 版本主要允许：
        search_matplotlib_knowledge
        list_matplotlib_course_documents

    后续升级多 Agent 时，这里可以进一步改造成：
        ToolRegistry / ToolRouter / AgentToolPolicy
    """

    if selected_tool_names:
        selected = set(selected_tool_names)
        return [
            tool
            for tool in all_tools
            if getattr(tool, "name", "") in selected
        ]

    allowed_names = {
        "search_matplotlib_knowledge",
        "list_matplotlib_course_documents",
    }

    return [
        tool
        for tool in all_tools
        if getattr(tool, "name", "") in allowed_names
    ]


# =============================================================================
# 4. MCP 工具调用辅助
# =============================================================================

def _extract_tool_query(tool_call: dict[str, Any]) -> str:
    """从 LangChain tool_call 中提取 query。"""

    args = tool_call.get("args", {})

    if not isinstance(args, dict):
        return ""

    query = args.get("query")

    if query is None:
        return ""

    return str(query)


def _extract_tool_result_content(result: Any) -> str:
    """
    将 MCP / LangChain 工具返回值统一转换为字符串。
    """

    if isinstance(result, ToolMessage):
        return serialize_tool_content(result.content)

    return serialize_tool_content(result)


def _extract_retrieved_documents(tool_result: str) -> list[Document]:
    """
    从 search_matplotlib_knowledge 返回值中提取检索结果。

    MCP 当前返回结构：

    {
        "knowledge_base_id": "...",
        "queries": [...],
        "results": [...]
    }

    这里主要负责将结果转换为 UI 可以继续处理的结构。
    """

    try:
        parsed = json.loads(tool_result)
    except (TypeError, json.JSONDecodeError):
        return []

    # MCP adapters return text content blocks; cached results keep that shape.
    payloads = []
    if isinstance(parsed, dict):
        payloads.append(parsed)
    elif isinstance(parsed, list):
        for block in parsed:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            try:
                payloads.append(json.loads(block.get("text")))
            except (TypeError, json.JSONDecodeError):
                continue

    documents = []
    for payload in payloads:
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            continue
        for item in payload["results"]:
            if not isinstance(item, dict) or not isinstance(item.get("content"), str):
                continue
            metadata = item.get("metadata")
            if metadata is None:
                metadata = {}
            if not isinstance(metadata, dict):
                continue
            metadata = dict(metadata)
            for key in ("type", "summary"):
                if key not in metadata and isinstance(item.get(key), str):
                    metadata[key] = item[key]
            documents.append(Document(page_content=item["content"], metadata=metadata))
    return documents


# =============================================================================
# 5. Agent Node
# =============================================================================

def agent_node(
    state: AgentState,
    *,
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    原单 Agent 的核心 ReAct 节点。

    工作流程：

        当前 State
            ↓
        获取当前用户角色
            ↓
        获取 MCP 工具
            ↓
        构建上下文
            ↓
        LLM + Tools
            ↓
        AIMessage
            ↓
        返回 LangGraph State
    """

    config = config or {}

    configurable = config.get("configurable", {})

    session_id = str(
        configurable.get("session_id", "")
    )

    user_role = str(
        configurable.get("user_role", "user")
    )

    all_tools = get_mcp_tools(
        context=configurable["session_context"],
        token_window=int(time.time()) // MCP_TOKEN_TTL_SECONDS,
    )

    selected_tool_names = state.get(
        "selected_tool_names",
        [],
    )

    tools = select_agent_tools(
        all_tools,
        selected_tool_names or None,
    )

    messages = list(state.get("messages", []))

    # -------------------------------------------------------------------------
    # 当前用户问题
    # -------------------------------------------------------------------------

    effective_messages = prepare_effective_messages(
        messages,
        session_id,
    )

    dynamic_system_prompt = build_system_prompt(
        user_role
    )

    # -------------------------------------------------------------------------
    # 上下文预算控制
    # -------------------------------------------------------------------------

    context_messages = build_model_context(
        dynamic_system_prompt=dynamic_system_prompt,
        messages=effective_messages,
        session_id=session_id,
        tools=tools,
    )

    # -------------------------------------------------------------------------
    # 绑定工具
    # -------------------------------------------------------------------------

    model = get_text_llm()

    if tools:
        model = model.bind_tools(tools)

    LOGGER.info(
        "Agent node 执行：session=%s role=%s tools=%s messages=%d",
        session_id,
        user_role,
        [getattr(tool, "name", "") for tool in tools],
        len(context_messages),
    )

    # -------------------------------------------------------------------------
    # 调用模型
    # -------------------------------------------------------------------------

    response = model.invoke(
        context_messages,
        config=config,
    )

    if not isinstance(response, AIMessage):
        response = AIMessage(
            content=str(response)
        )

    return {
        "messages": [response],
        "step_count": state.get("step_count", 0) + 1,
    }


# =============================================================================
# 6. Selected Tool Node
# =============================================================================

def selected_tool_node(
    state: AgentState,
    *,
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    执行当前 Agent 选择的工具。

    当前版本主要处理 MCP 工具。

    同时保留原来的：
        Redis Tool Result Cache

    对 search_matplotlib_knowledge：
        query
          ↓
        Redis Cache
          ↓
        命中 → 直接返回
        未命中 → 调用 MCP
          ↓
        写入 Cache
    """

    config = config or {}

    configurable = config.get(
        "configurable",
        {},
    )

    session_id = str(
        configurable.get("session_id", "")
    )

    messages = list(
        state.get("messages", [])
    )

    if not messages:
        return {}

    last_message = messages[-1]

    if not isinstance(last_message, AIMessage):
        return {}

    tool_calls = last_message.tool_calls

    if not tool_calls:
        return {}

    all_tools = get_mcp_tools(
        context=configurable["session_context"],
        token_window=int(time.time()) // MCP_TOKEN_TTL_SECONDS,
    )

    tools = select_agent_tools(
        all_tools,
        state.get("selected_tool_names") or None,
    )

    tool_map = {
        getattr(tool, "name", ""): tool
        for tool in tools
    }

    tool_messages: list[ToolMessage] = []
    retrieved_docs: list[Any] = list(
        state.get("retrieved_docs", [])
    )

    for tool_call in tool_calls:

        tool_name = str(
            tool_call.get("name", "")
        )

        tool = tool_map.get(tool_name)

        if tool is None:
            tool_messages.append(
                ToolMessage(
                    content=f"工具 {tool_name} 不在当前 Agent 的允许工具列表中。",
                    tool_call_id=tool_call.get("id", ""),
                    name=tool_name,
                )
            )
            continue

        query = _extract_tool_query(
            tool_call
        )

        # ---------------------------------------------------------------------
        # Redis 工具缓存
        # ---------------------------------------------------------------------

        cached_result = get_cached_tool_result(
            session_id=session_id,
            tool_name=tool_name,
            query=query,
        )

        if cached_result is not None:
            LOGGER.info(
                "命中工具结果缓存：session=%s tool=%s",
                session_id,
                tool_name,
            )

            tool_result = cached_result

        else:
            try:
                args = tool_call.get(
                    "args",
                    {},
                )

                # MCP 工具本身可能是异步 Runnable。
                result = run_coroutine_sync(
                    tool.ainvoke(
                        args,
                        config=config,
                    )
                )

                tool_result = _extract_tool_result_content(
                    result
                )

                # 仅对允许缓存的知识检索工具写缓存。
                set_cached_tool_result(
                    session_id=session_id,
                    tool_name=tool_name,
                    query=query,
                    result=tool_result,
                )

            except Exception as exc:
                LOGGER.exception(
                    "工具调用失败：tool=%s",
                    tool_name,
                )

                tool_result = (
                    f"工具调用失败：{tool_name}\n"
                    f"错误：{exc}"
                )

        # ---------------------------------------------------------------------
        # 构造 ToolMessage
        # ---------------------------------------------------------------------

        tool_messages.append(
            ToolMessage(
                content=tool_result,
                tool_call_id=tool_call.get(
                    "id",
                    "",
                ),
                name=tool_name,
            )
        )

        # ---------------------------------------------------------------------
        # 保存知识库检索结果，供 UI 展示
        # ---------------------------------------------------------------------

        if tool_name == "search_matplotlib_knowledge":
            documents = _extract_retrieved_documents(
                tool_result
            )

            if documents:
                retrieved_docs.extend(
                    documents
                )

    return {
        "messages": tool_messages,
        "retrieved_docs": retrieved_docs,
    }


# =============================================================================
# 7. 条件路由
# =============================================================================

def should_continue(
    state: AgentState,
) -> str:
    """
    判断 ReAct 循环是否继续。

    路由：

        AI 没有 tool_calls
            ↓
           END

        AI 有 tool_calls
            ↓
        selected_tool_node

    同时增加最大步数保护。
    """

    messages = state.get(
        "messages",
        [],
    )

    if not messages:
        return END

    step_count = int(
        state.get(
            "step_count",
            0,
        )
    )

    max_steps = int(
        state.get(
            "max_steps",
            MAX_AGENT_STEPS,
        )
    )

    last_message = messages[-1]

    if isinstance(
        last_message,
        AIMessage,
    ):
        if last_message.tool_calls:
            if step_count >= max_steps:
                LOGGER.warning("Agent 达到最大执行步数：%d", max_steps)
                return END
            return "selected_tool_node"

    return END


# =============================================================================
# 8. LangGraph 构建
# =============================================================================

def build_agent_app():
    """
    构建并编译原单 Agent LangGraph。

    当前图：

        START
          ↓
        agent
          ↓
        should_continue
        ↙          ↘
    ToolNode       END
        ↓
       agent

    注意：
        当前阶段保留单 Agent 结构。
        后续多 Agent 升级时，再将这里扩展为 Supervisor / 子图结构。
    """

    workflow = StateGraph(
        AgentState
    )

    workflow.add_node(
        "agent",
        agent_node,
    )

    workflow.add_node(
        "selected_tool_node",
        selected_tool_node,
    )

    workflow.add_edge(
        START,
        "agent",
    )

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "selected_tool_node": "selected_tool_node",
            END: END,
        },
    )

    workflow.add_edge(
        "selected_tool_node",
        "agent",
    )

    return workflow.compile()


# =============================================================================
# 9. Input Adapter
# =============================================================================

def input_adapter(
    question: str,
    *,
    session_id: str,
    user_id: str,
    knowledge_base_id: str,
    user_role: str = "user",
) -> dict[str, Any]:
    """
    将 UI 输入转换成 LangGraph State。

    UI 不需要知道 AgentState 的内部结构。
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError("question 必须是非空字符串。")

    return {
        "messages": [
            HumanMessage(
                content=question
            )
        ],
        "turn_start": 0,
        "step_count": 0,
        "max_steps": MAX_AGENT_STEPS,
        "retrieved_docs": [],
        "selected_tool_names": [
            "search_matplotlib_knowledge",
            "list_matplotlib_course_documents",
        ],
    }


# =============================================================================
# 10. Output Adapter
# =============================================================================

def output_adapter(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    映射本轮最终结果，并提供历史包装器需要写回的增量消息。

    _history_messages 仅供包装器使用，对外返回前移除；不重复写回历史
    或当前 HumanMessage（后者由 RunnableWithMessageHistory 写入）。
    """

    messages = state.get("messages", [])
    generated = list(messages[state.get("turn_start", 0) + 1:])
    last_message = generated[-1] if generated else None
    completed = (
        isinstance(last_message, AIMessage)
        and not last_message.tool_calls
        and bool(last_message.content)
        and bool(str(last_message.content).strip())
    )
    error = None
    if completed:
        answer = str(last_message.content)
    else:
        pending_calls = (
            last_message.tool_calls if isinstance(last_message, AIMessage) else []
        )
        exhausted = bool(pending_calls) and state.get("step_count", 0) >= state.get(
            "max_steps", MAX_AGENT_STEPS
        )
        error = "max_steps_exceeded" if exhausted else "no_final_answer"
        answer = (
            "本轮任务未完成：已达到最大执行步数，仍有工具调用未执行。请缩小问题范围后重试。"
            if exhausted else "本轮任务未完成：未获得有效的最终回答，请重试。"
        )
        # 记录取消而非伪造工具成功，避免未配对调用污染后续轮次。
        generated.extend(
            ToolMessage(
                content="工具调用未执行：本轮任务已结束。",
                tool_call_id=call["id"],
                name=call["name"],
                status="error",
            )
            for call in pending_calls
        )
        generated.append(AIMessage(content=answer))

    return {
        "answer": answer,
        "retrieved_docs": state.get("retrieved_docs", []),
        "status": "completed" if completed else "incomplete",
        "error": error,
        "_history_messages": generated,
    }


# =============================================================================
# 11. Graph Singleton
# =============================================================================

_agent_app = None


def get_agent_app():
    """
    获取全局编译后的 LangGraph。

    避免每次用户请求重新编译 Graph。
    """

    global _agent_app

    if _agent_app is None:
        LOGGER.info(
            "首次创建 LangGraph Agent。"
        )
        _agent_app = build_agent_app()

    return _agent_app


# =============================================================================
# 12. RunnableWithMessageHistory
# =============================================================================

def get_rag_chain_with_memory(
    session_context,
):
    """
    对外接收 {"question": str}，返回 answer/retrieved_docs/status/error。

    历史通过独立 history 字段注入，再与当前问题合并进入图。
    Redis 持久化仍由原历史包装器和 memory.py 管理。
    """

    session_id = (
        session_context.redis_session_id
    )

    user_id = (
        session_context.user_id
    )

    knowledge_base_id = (
        session_context.knowledge_base_id
    )

    graph = get_agent_app().with_config(
        configurable={
            "session_context": session_context,
            "session_id": session_id,
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
        },
    )

    def prepare_input(value: dict[str, Any]) -> dict[str, Any]:
        # 在读取历史之前校验；复用既有适配器，不允许输入覆盖内部 State。
        if not isinstance(value, dict):
            raise ValueError("Agent 输入必须是包含 question 的字典。")
        state = input_adapter(
            value.get("question"),
            session_id=session_id,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
        )
        return {"question": value["question"], "_input_state": state}

    def attach_history(value: dict[str, Any]) -> dict[str, Any]:
        state = dict(value["_input_state"])
        history = list(value["history"])
        state["messages"] = history + state["messages"]
        state["turn_start"] = len(history)
        return state

    def get_history(
        _session_id: str,
    ):
        if _session_id != session_id:
            raise ValueError("session_id 与当前会话上下文不一致。")
        return get_session_history(
            session_id
        )

    # -------------------------------------------------------------------------
    # 使用 RunnableWithMessageHistory 将 Redis 接入 LangGraph。
    #
    # 注意：
    # LangGraph 自己维护 messages State；
    # RunnableWithMessageHistory 负责提供外部持久化历史。
    # -------------------------------------------------------------------------

    runnable = RunnableWithMessageHistory(
        RunnableLambda(attach_history) | graph | RunnableLambda(output_adapter),
        get_history,
        input_messages_key="question",
        history_messages_key="history",
        output_messages_key="_history_messages",
    )

    return (
        RunnableLambda(prepare_input)
        | runnable
        | RunnableLambda(lambda result: {
            key: value for key, value in result.items() if key != "_history_messages"
        })
    ).with_config(configurable={"session_id": session_id})


# =============================================================================
# 13. 对外统一调用接口
# =============================================================================

def invoke_agent(
    question: str,
    session_context,
    *,
    user_role: str = "user",
    callbacks: list[Any] | None = None,
) -> dict[str, Any]:
    """
    给上层 UI / API 使用的统一 Agent 调用入口。

    UI 不需要知道：

        AgentState
        LangGraph
        ToolNode
        MCP
        Redis
        Prompt

    这些都封装在 agent.py 内部。
    """

    session_id = (
        session_context.redis_session_id
    )

    user_id = (
        session_context.user_id
    )

    knowledge_base_id = (
        session_context.knowledge_base_id
    )

    chain = get_rag_chain_with_memory(
        session_context
    )

    config = {
        "configurable": {
            "session_id": session_id,
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "user_role": user_role,
        }
    }

    if callbacks:
        config["callbacks"] = callbacks

    return chain.invoke(
        {"question": question},
        config=config,
    )


__all__ = [
    "AgentState",
    "SYSTEM_PROMPT",
    "build_system_prompt",
    "select_agent_tools",
    "agent_node",
    "selected_tool_node",
    "should_continue",
    "build_agent_app",
    "get_agent_app",
    "input_adapter",
    "output_adapter",
    "get_rag_chain_with_memory",
    "invoke_agent",
]
