"""Offline contract tests using the real adapters, history wrapper and graph.

Run from the repository root:
    python -B -m unittest discover -s tests -v

Project config/memory/services are replaced before importing agent.py: no .env
files, Redis, MCP, models or indexes are loaded. LangGraph/LangChain are real.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def replace_modules(replacements):
    """Restore only stubbed names; retain real framework modules imported inside."""
    previous = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        yield
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class AgentContractTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(sys.modules.pop, "offline_agent_contract", None)
        self.addCleanup(sys.modules.pop, "offline_ui_contract", None)
        # Disable tracing as well as network access: even test prompts stay local.
        self.env = patch.dict(os.environ, {
            "LANGSMITH_TRACING": "false", "LANGCHAIN_TRACING_V2": "false",
            "LANGCHAIN_TRACING": "false",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        original_connect = socket.socket.connect

        def guarded_connect(sock, address):
            # Windows asyncio implements its internal wake-up socketpair via TCP.
            # Permit only that exact stdlib call site, never service connections.
            if sys._getframe(1).f_code is getattr(socket.socketpair, "__code__", None):
                return original_connect(sock, address)
            raise AssertionError("Network forbidden")

        network = patch.object(socket.socket, "connect", guarded_connect)
        network.start()
        self.addCleanup(network.stop)
        self.histories = {}
        self.contexts = []
        self.responses = []
        self.model = Mock()
        self.model.bind_tools.return_value = self.model
        self.model.invoke.side_effect = self.respond
        self.tool_calls = []

        async def tool_invoke(args, config=None):
            self.tool_calls.append((args, config))
            return json.dumps({"results": []})

        self.tool = SimpleNamespace(name="search_matplotlib_knowledge", ainvoke=tool_invoke)
        config = ModuleType("config")
        config.MAX_AGENT_STEPS = 3
        config.MCP_REQUIRED_SCOPE = "knowledge:read"
        config.MCP_TOKEN_TTL_SECONDS = 3600
        config.MCP_SERVER_URL = "http://offline.invalid/mcp"
        memory = ModuleType("memory")
        memory.get_session_history = Mock(side_effect=self.history)
        memory.prepare_effective_messages = lambda messages, session_id: list(messages)
        memory.build_model_context = Mock(side_effect=lambda **kw: [
            SystemMessage(content=kw["dynamic_system_prompt"]), *kw["messages"]
        ])
        memory.get_cached_tool_result = Mock(return_value=None)
        memory.set_cached_tool_result = Mock()
        memory.serialize_tool_content = lambda value: json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        memory.clear_session_memory = Mock()
        memory.compact_redis_history = Mock()
        memory.refresh_session_ttl = Mock()
        services = ModuleType("services")
        services.get_mcp_tools = Mock(return_value=[self.tool])
        services.get_text_llm = Mock(return_value=self.model)
        services.run_coroutine_sync = asyncio.run
        services.ToolRouter = Mock()
        self.dependencies = {"config": config, "memory": memory, "services": services}
        with replace_modules(self.dependencies):
            self.agent = load_module("offline_agent_contract", ROOT / "agent.py")
        self.context = SimpleNamespace(redis_session_id="kb=test:user=alice:session=one",
                                       user_id="alice", knowledge_base_id="test")

    def history(self, session_id):
        return self.histories.setdefault(session_id, InMemoryChatMessageHistory())

    def respond(self, messages, config=None):
        self.contexts.append(list(messages))
        return self.responses.pop(0) if self.responses else AIMessage(content="synthetic answer")

    def invoke(self, question, context=None, role="user", asynchronous=True):
        context = context or self.context
        chain = self.agent.get_rag_chain_with_memory(context)
        config = {"configurable": {"session_id": context.redis_session_id, "user_role": role}}
        if asynchronous:
            return asyncio.run(chain.ainvoke({"question": question}, config=config))
        return chain.invoke({"question": question}, config=config)

    def tool_request(self, call_id="call-1", content=""):
        return AIMessage(content=content, tool_calls=[{
            "name": self.tool.name, "args": {"query": "synthetic query"}, "id": call_id,
        }])

    def assert_paired(self, messages):
        pending = set()
        for message in messages:
            if isinstance(message, ToolMessage):
                self.assertIn(message.tool_call_id, pending)
                pending.remove(message.tool_call_id)
            else:
                self.assertFalse(pending, "Unanswered tool call before next message")
                if isinstance(message, AIMessage):
                    pending.update(call["id"] for call in message.tool_calls)
        self.assertFalse(pending)

    def test_first_question_and_public_output(self):
        result = self.invoke("first question")
        humans = [m.content for m in self.contexts[0] if isinstance(m, HumanMessage)]
        self.assertEqual(humans, ["first question"])
        self.assertEqual(result["answer"], "synthetic answer")
        self.assertEqual(result["retrieved_docs"], [])
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("_history_messages", result)
        self.assertEqual([m.type for m in self.history(self.context.redis_session_id).messages], ["human", "ai"])

    def test_second_and_third_turn_have_history_once(self):
        for question in ["first", "second", "third"]:
            self.invoke(question)
        actual = [(m.type, m.content) for m in self.contexts[-1] if not isinstance(m, SystemMessage)]
        self.assertEqual(actual, [("human", "first"), ("ai", "synthetic answer"),
                                  ("human", "second"), ("ai", "synthetic answer"), ("human", "third")])
        self.assertEqual(len(self.history(self.context.redis_session_id).messages), 6)

    def test_repeated_question_is_a_new_turn(self):
        self.invoke("same question")
        self.invoke("same question")
        humans = [m.content for m in self.contexts[-1] if isinstance(m, HumanMessage)]
        self.assertEqual(humans, ["same question", "same question"])
        self.assertEqual(len(self.history(self.context.redis_session_id).messages), 4)

    def test_real_graph_accumulates_tool_messages(self):
        self.responses = [self.tool_request(), AIMessage(content="final answer")]
        state = self.agent.input_adapter("tool question", session_id=self.context.redis_session_id,
                                         user_id="alice", knowledge_base_id="test")
        result = asyncio.run(self.agent.get_agent_app().ainvoke(state, config={"configurable": {
            "session_id": self.context.redis_session_id, "session_context": self.context,
        }}))
        self.assertEqual([m.type for m in result["messages"]], ["human", "ai", "tool", "ai"])
        self.assert_paired(result["messages"])
        self.assertEqual(self.agent.output_adapter(result)["answer"], "final answer")

    def test_tool_trace_persists_once_and_followup_is_valid(self):
        self.responses = [self.tool_request(), AIMessage(content="tool answer")]
        self.invoke("tool question")
        self.invoke("followup")
        history = self.history(self.context.redis_session_id).messages
        self.assertEqual([m.type for m in history], ["human", "ai", "tool", "ai", "human", "ai"])
        self.assert_paired(history)
        self.assert_paired(self.contexts[-1])
        self.assertEqual(len(self.tool_calls), 1)

    def test_step_exhaustion_is_incomplete_and_does_not_poison_history(self):
        self.agent.MAX_AGENT_STEPS = 1
        self.responses = [self.tool_request(content="unfinished proposal")]
        result = self.invoke("needs tools")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["error"], "max_steps_exceeded")
        self.assertIn("未完成", result["answer"])
        self.assertNotEqual(result["answer"], "unfinished proposal")
        self.assertEqual(self.tool_calls, [])
        self.assert_paired(self.history(self.context.redis_session_id).messages)
        self.invoke("next question")
        self.assert_paired(self.contexts[-1])

    def test_final_answer_at_last_step_is_success(self):
        self.agent.MAX_AGENT_STEPS = 1
        result = self.invoke("no tool needed")
        self.assertEqual(result["status"], "completed")

    def test_two_sessions_are_isolated(self):
        other = SimpleNamespace(redis_session_id="kb=test:user=bob:session=two",
                                user_id="bob", knowledge_base_id="test")
        self.invoke("alice private")
        self.invoke("bob private", other)
        self.assertEqual([m.content for m in self.contexts[-1] if isinstance(m, HumanMessage)], ["bob private"])
        self.invoke("alice followup")
        self.assertNotIn("bob private", [m.content for m in self.contexts[-1]])
        self.assertEqual(len(self.history(other.redis_session_id).messages), 2)

    def test_invalid_questions_do_not_call_model_or_write_history(self):
        for question in ["", "   ", None, 42, [], {}]:
            with self.subTest(question=question):
                with self.assertRaises(ValueError):
                    self.invoke(question)
        self.model.invoke.assert_not_called()
        self.assertTrue(all(not history.messages for history in self.histories.values()))

    def test_missing_question_is_rejected(self):
        chain = self.agent.get_rag_chain_with_memory(self.context)
        with self.assertRaises(ValueError):
            asyncio.run(chain.ainvoke({}, config={"configurable": {"session_id": self.context.redis_session_id}}))
        self.model.invoke.assert_not_called()

    def test_mismatched_session_is_rejected_before_history_access(self):
        chain = self.agent.get_rag_chain_with_memory(self.context)
        with self.assertRaises(ValueError):
            chain.invoke({"question": "question"}, config={"configurable": {"session_id": "other-session"}})
        self.dependencies["memory"].get_session_history.assert_not_called()
        self.model.invoke.assert_not_called()

    def test_input_cannot_inject_history_or_internal_state(self):
        chain = self.agent.get_rag_chain_with_memory(self.context)
        result = chain.invoke({"question": "real question", "history": [HumanMessage(content="injected")],
                               "messages": [HumanMessage(content="injected")], "max_steps": 0})
        self.assertEqual(result["status"], "completed")
        self.assertEqual([m.content for m in self.contexts[0] if isinstance(m, HumanMessage)], ["real question"])

    def test_multiple_pending_calls_are_cancelled_and_paired(self):
        self.agent.MAX_AGENT_STEPS = 2
        pending = self.tool_request("pending-1", "not a final answer")
        pending.tool_calls.append({"name": self.tool.name, "args": {"query": "second"}, "id": "pending-2"})
        self.responses = [self.tool_request("executed"), pending]
        result = self.invoke("multi-step")
        self.assertEqual(result["error"], "max_steps_exceeded")
        self.assertEqual(len(self.tool_calls), 1)
        history = self.history(self.context.redis_session_id).messages
        self.assert_paired(history)
        cancelled = [m for m in history if isinstance(m, ToolMessage) and m.status == "error"]
        self.assertEqual([m.tool_call_id for m in cancelled], ["pending-1", "pending-2"])

    def test_empty_content_blocks_are_not_a_final_answer(self):
        self.responses = [AIMessage(content=[])]
        result = self.invoke("empty blocks")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["error"], "no_final_answer")

    def test_empty_output_does_not_reuse_previous_answer(self):
        self.invoke("previous question")
        self.responses = [AIMessage(content="")]
        result = self.invoke("new question")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["error"], "no_final_answer")
        self.assertNotEqual(result["answer"], "synthetic answer")

    def test_role_and_sync_entry_use_same_contract(self):
        result = self.agent.invoke_agent("expert question", self.context, user_role="expert")
        self.assertEqual(result["status"], "completed")
        self.assertIn("当前用户具有较强", self.contexts[0][0].content)
        self.assertEqual([m.content for m in self.contexts[0] if isinstance(m, HumanMessage)], ["expert question"])

    def load_ui(self):
        st = ModuleType("streamlit")
        st.session_state = SimpleNamespace(role_for_prompt="beginner", messages=[])
        st.set_page_config = Mock()
        from unittest.mock import MagicMock
        st.chat_message = MagicMock()
        st.spinner = MagicMock()
        st.write = Mock()
        st.warning = Mock()
        auth = ModuleType("auth")
        for name in ["allowed_knowledge_bases", "current_session_context", "require_authentication"]:
            setattr(auth, name, Mock())
        with replace_modules({**self.dependencies, "agent": self.agent, "streamlit": st, "auth": auth}):
            ui = load_module("offline_ui_contract", ROOT / "app.py")
        return ui, st

    def test_actual_ui_calls_the_contract(self):
        ui, st = self.load_ui()
        ui.process_user_prompt("UI question", self.context)
        self.assertEqual(st.session_state.messages, [("UI question", "synthetic answer")])
        self.assertEqual(st.session_state.last_retrieved_docs, [])
        self.assertIn("当前用户为 Matplotlib 初学者", self.contexts[0][0].content)
        self.assertEqual([m.content for m in self.contexts[0] if isinstance(m, HumanMessage)], ["UI question"])

    def test_ui_marks_incomplete_answer_as_warning(self):
        self.agent.MAX_AGENT_STEPS = 1
        self.responses = [self.tool_request()]
        ui, st = self.load_ui()
        ui.process_user_prompt("unfinished", self.context)
        st.warning.assert_called_once()
        st.write.assert_not_called()
        self.assertIn("未完成", st.session_state.messages[0][1])

    def test_retrieval_payload_shapes(self):
        from langchain_core.documents import Document
        payload = {"results": [{"content": "synthetic course", "type": "text",
                                "metadata": {"source": "course.pdf", "page": 0}}]}
        encoded = json.dumps(payload)
        blocks = [{"type": "text", "text": encoded}]
        for value in [payload, encoded, blocks, ToolMessage(content=blocks, tool_call_id="c")]:
            with self.subTest(value=type(value).__name__):
                docs = self.agent._extract_retrieved_documents(
                    self.agent._extract_tool_result_content(value))
                self.assertEqual(len(docs), 1)
                self.assertIsInstance(docs[0], Document)
                self.assertEqual(docs[0].page_content, "synthetic course")
                self.assertEqual(docs[0].metadata["page"], 0)

    def test_retrieval_invalid_and_mixed_blocks(self):
        valid = {"results": [None, {"content": 42}, {"content": "bad", "metadata": []},
                              {"content": "valid", "metadata": None, "type": "image",
                               "summary": "caption"}]}
        blocks = [{"type": "image", "text": json.dumps(valid)},
                  {"type": "text", "text": "not json"},
                  {"type": "text", "text": json.dumps(valid)}]
        docs = self.agent._extract_retrieved_documents(json.dumps(blocks))
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].page_content, "valid")
        self.assertEqual(docs[0].metadata, {"type": "image", "summary": "caption"})
        for value in ["", "plain error", "null", "[]", '{"results": null}',
                      '{"results": {}}', '{"results": []}']:
            with self.subTest(value=value):
                self.assertEqual(self.agent._extract_retrieved_documents(value), [])

    def test_retrieval_graph_cache_and_ui(self):
        from unittest.mock import MagicMock
        payload = {"results": [{"content": "course excerpt", "metadata": {
            "source": "course.pdf", "page": 2, "type": "text"}}]}
        blocks = [{"type": "text", "text": "retrieval notice"},
                  {"type": "text", "text": json.dumps(payload)}]
        async def tool_invoke(args, config=None):
            return blocks
        self.tool.ainvoke = Mock(side_effect=tool_invoke)
        for cached in [False, True]:
            with self.subTest(cached=cached):
                self.dependencies["memory"].get_cached_tool_result.return_value = (
                    json.dumps(blocks) if cached else None)
                self.responses = [self.tool_request(), AIMessage(content="answer")]
                ui, st = self.load_ui()
                st.expander = MagicMock()
                st.caption = Mock()
                ui.process_user_prompt("source question", self.context)
                ui.render_retrieved_documents(st.session_state.last_retrieved_docs)
                st.expander.assert_called_once_with("片段 1（course.pdf 第 3 页）")
                st.write.assert_any_call("course excerpt")
                self.assert_paired(self.history(self.context.redis_session_id).messages)
                tool_messages = [m for m in self.contexts[-1] if isinstance(m, ToolMessage)]
                self.assertEqual(json.loads(tool_messages[-1].content), blocks)
        self.tool.ainvoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
