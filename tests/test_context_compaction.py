# -*- coding: utf-8 -*-
"""压缩的消息完整性、失败保留和聊天回滚测试；不读取密钥或调用外部 API。"""

import copy
import importlib.util
import io
import json
import pathlib
import types
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUMMARY = "## Objective\n- Modify the project.\n## Requirements\n- Preserve GBK."


def load(name, filename, modules):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    with patch.dict("sys.modules", modules):
        spec.loader.exec_module(module)
    return module


def response(text=SUMMARY, finish="stop", delta=None):
    yield b'data: {"choices": [], "usage": {"prompt_tokens": 1}}'
    packet = {"choices": [{"delta": delta or {"content": text}, "finish_reason": finish}]}
    yield b"data: " + json.dumps(packet).encode("utf-8")
    yield b"data: [DONE]"


def history():
    return [
        {"role": "system", "content": "Keep the system instructions."},
        {"role": "user", "content": "old request " * 1000},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "old", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "old", "content": "old GBK result " * 1000},
        {"role": "assistant", "content": "completed"},
        {"role": "user", "content": "current task"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "current", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "current", "content": "current exact content"},
    ]


class CompactionTests(unittest.TestCase):
    def setUp(self):
        self.config = types.SimpleNamespace(
            ROOT=str(ROOT), MAX_CHARS=8000, MAX_WRITES=10,
            CONTEXT_TOKENS=8000, KEEP_TOKENS=100, SUMMARY_TOKENS=512,
            API="http://unused.invalid", KEY="test-only", MODEL="test-model", THRESH=5, COOL=60,
        )
        self.api = types.SimpleNamespace(STOP=False, EXIT=False)
        self.api.check_control = lambda: self.api.STOP
        self.api.network_lines = Mock(side_effect=lambda *args, **kwargs: response())
        self.files = types.SimpleNamespace(TOOLS=[], WT=(), run=Mock())
        self.modules = {"config": self.config, "api_client": self.api, "file_tools": self.files}
        self.module = load("test_compaction", "context_compaction.py", self.modules)
        self.compactor = self.module.ContextCompactor()
        self.output = io.StringIO()
        self.capture = patch("sys.stdout", self.output)
        self.capture.start()
        self.addCleanup(self.capture.stop)

    def test_summary_receives_old_tools_and_preserves_current_round(self):
        messages = history()
        system, recent = copy.deepcopy(messages[0]), copy.deepcopy(messages[5:])
        self.assertTrue(self.compactor.compact(messages))
        self.assertEqual(messages[0], system)
        self.assertEqual(messages[2:], recent)
        request = self.api.network_lines.call_args
        older = json.loads(request.args[0][1]["content"])
        self.assertEqual(older, history()[1:5])
        self.assertFalse(request.kwargs["with_tools"])
        self.assertEqual(request.kwargs["max_tokens"], 512)

    def test_rolling_summary_carries_previous_checkpoint(self):
        messages = history()
        self.assertTrue(self.compactor.compact(messages, force=True))
        first = copy.deepcopy(messages[1])
        messages.extend([
            {"role": "assistant", "content": "more progress " * 1000},
            {"role": "user", "content": "new task"},
        ])
        self.assertTrue(self.compactor.compact(messages, force=True))
        request = self.api.network_lines.call_args.args[0]
        self.assertIn("Update the existing checkpoint", request[0]["content"])
        self.assertEqual(json.loads(request[1]["content"])[0], first)
        self.assertEqual(sum("<conversation-checkpoint>" in (m.get("content") or "") for m in messages), 1)
        self.assertEqual(messages[-1]["content"], "new task")

    def test_failed_summaries_keep_every_message_and_do_not_retry_in_turn(self):
        failures = [
            lambda: response(text=""),
            lambda: response(finish="length"),
            lambda: response(finish=None),
            lambda: response(text="unstructured text"),
            lambda: response(delta={"tool_calls": [{"id": "unexpected"}]}),
            lambda: response(text=SUMMARY + "x" * 100000),
        ]
        for failure in failures:
            with self.subTest(failure=failure):
                compactor = self.module.ContextCompactor()
                messages = history()
                before = copy.deepcopy(messages)
                self.api.network_lines.reset_mock()
                self.api.network_lines.side_effect = lambda *a, **k: failure()
                self.assertFalse(compactor.compact(messages))
                self.assertEqual(messages, before)
                self.assertFalse(compactor.compact(messages))
                self.assertEqual(self.api.network_lines.call_count, 1)

    def test_network_error_stop_and_keyboard_interrupt_keep_history(self):
        for failure in (RuntimeError("offline"), KeyboardInterrupt()):
            compactor = self.module.ContextCompactor()
            messages = history()
            before = copy.deepcopy(messages)
            self.api.STOP = False
            self.api.network_lines.side_effect = failure
            self.assertFalse(compactor.compact(messages, force=True))
            self.assertEqual(messages, before)
        self.api.STOP = False
        self.api.network_lines.side_effect = lambda *a, **k: response()
        self.api.check_control = lambda: True
        messages = history()
        before = copy.deepcopy(messages)
        self.assertFalse(self.compactor.compact(messages, force=True))
        self.assertEqual(messages, before)

    def test_small_history_single_round_and_disabled_automatic_compaction(self):
        self.assertFalse(self.compactor.compact([{"role": "system", "content": "system"}]))
        self.assertFalse(self.compactor.compact(history()[:5], force=True))
        self.compactor.window = 0
        self.assertFalse(self.compactor.compact(history()))
        self.api.network_lines.assert_not_called()
        self.assertTrue(self.compactor.compact(history(), force=True))

    def test_current_round_larger_than_keep_is_not_split(self):
        messages = history()
        messages[-1]["content"] = "large current tool result " * 1000
        recent = copy.deepcopy(messages[5:])
        self.assertTrue(self.compactor.compact(messages, force=True))
        self.assertEqual(messages[2:], recent)

    def test_chat_rolls_back_current_response_after_compaction(self):
        prompts = iter(["old task one", "old task two", "current task", "/exit"])
        terminal = types.SimpleNamespace(read_prompt=lambda: next(prompts), show_action=Mock(), show_result=Mock())
        state = {"calls": 0}

        def stream(messages):
            state["messages"] = messages
            state["calls"] += 1
            messages.append({"role": "assistant", "content": "old details " * 1000 if state["calls"] < 3 else "partial response"})
            if state["calls"] == 3:
                self.api.STOP = True
            return "", []

        self.api.stream = stream
        modules = dict(self.modules, terminal=terminal, context_compaction=self.module)
        chat = load("test_compaction_chat", "chat.py", modules)
        chat.main()
        messages = state["messages"]
        self.assertEqual(len(messages), 3)
        self.assertIn("<conversation-checkpoint>", messages[1]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "current task"})
        self.assertIn("[Turn discarded]", self.output.getvalue())

    def test_manual_command_works_with_automatic_compaction_disabled(self):
        self.config.CONTEXT_TOKENS = 0
        prompts = iter(["old task", "recent task", "/compact", "/exit"])
        terminal = types.SimpleNamespace(read_prompt=lambda: next(prompts), show_action=Mock(), show_result=Mock())
        state = {}

        def stream(messages):
            state["messages"] = messages
            messages.append({"role": "assistant", "content": "details " * 2000})
            return "", []

        self.api.stream = stream
        chat = load("test_manual_compaction_chat", "chat.py", dict(self.modules, terminal=terminal, context_compaction=self.module))
        chat.main()
        self.api.network_lines.assert_called_once()
        self.assertIn("<conversation-checkpoint>", state["messages"][1]["content"])

    def test_summary_transport_disables_tools_without_changing_normal_requests(self):
        response_object = types.SimpleNamespace(
            raise_for_status=Mock(), iter_lines=lambda **k: iter([b"data: [DONE]"]), close=Mock(),
        )
        requests = types.SimpleNamespace(post=Mock(return_value=response_object))
        terminal = types.SimpleNamespace(poll_control=lambda: None)
        api = load("test_summary_api", "api_client.py", dict(self.modules, terminal=terminal, requests=requests))
        messages = [{"role": "user", "content": "test"}]
        list(api.network_lines(messages, with_tools=False, max_tokens=512))
        payload = requests.post.call_args.kwargs["json"]
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["max_tokens"], 512)
        self.assertIsNot(payload["messages"], messages)
        list(api.network_lines(messages))
        payload = requests.post.call_args.kwargs["json"]
        self.assertIn("tools", payload)
        self.assertNotIn("max_tokens", payload)


if __name__ == "__main__":
    unittest.main()
