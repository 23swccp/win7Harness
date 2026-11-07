# -*- coding: utf-8 -*-
"""会话持久化与单轮工具调用限制。"""
import json
import importlib.util
import pathlib
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

# 测试使用公开模板，不依赖用户本地的 config.py。
spec = importlib.util.spec_from_file_location("config", pathlib.Path(__file__).resolve().parents[1] / "config.example.py")
test_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_config)
with patch.dict("sys.modules", {"config": test_config}):
    import chat


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(pathlib.Path(self.tmp.name) / "context.json")

    def test_restart_restores_messages_and_summary_with_current_system(self):
        old = [{"role": "system", "content": "old"}, {"role": "user", "content": "中文"}, {"role": "assistant", "content": "done"}]
        chat.save_context(self.path, old, types.SimpleNamespace(summary="checkpoint"))
        compactor = types.SimpleNamespace(summary="")
        current = {"role": "system", "content": "new"}
        self.assertEqual(chat.load_context(self.path, current, compactor), [current] + old[1:])
        self.assertEqual(compactor.summary, "checkpoint")

    def test_corrupt_context_is_not_overwritten(self):
        pathlib.Path(self.path).write_text("bad", encoding="utf-8")
        with self.assertRaises(ValueError):
            chat.load_context(self.path, {"role": "system", "content": ""}, types.SimpleNamespace(summary=""))
        self.assertEqual(pathlib.Path(self.path).read_text(encoding="utf-8"), "bad")

    def test_tool_limit_counts_calls_and_saves_complete_batch(self):
        calls = [{"id": str(i), "type": "function", "function": {"name": "read_file", "arguments": "{}"}} for i in range(3)]
        def stream(messages):
            messages.append({"role": "assistant", "content": None, "tool_calls": calls})
            return "", calls
        runner = Mock(return_value="result")
        with patch.object(chat.config, "CONTEXT_FILE", self.path, create=True), \
             patch.object(chat.config, "MAX_TOOL_CALLS", 2, create=True), \
             patch.object(chat, "read_prompt", side_effect=["task", "/exit"]), \
             patch.object(chat.api, "stream", side_effect=stream), \
             patch.object(chat.api, "check_control", return_value=False), \
             patch.object(chat, "run", runner), patch.object(chat, "show_action"), patch.object(chat, "show_result"):
            chat.api.STOP = chat.api.EXIT = False
            chat.main()
        self.assertEqual(runner.call_count, 2)
        messages = json.loads(pathlib.Path(self.path).read_text(encoding="utf-8"))["messages"]
        self.assertEqual([m["tool_call_id"] for m in messages if m["role"] == "tool"], ["0", "1", "2"])
        self.assertEqual(messages[-1]["content"], "Tool call limit reached")


if __name__ == "__main__":
    unittest.main()
