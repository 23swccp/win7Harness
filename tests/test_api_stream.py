# -*- coding: utf-8 -*-
"""流内错误、HTTP 错误正文及分段工具调用测试；不访问外部 API。"""

import importlib.util
import io
import json
import pathlib
import time
import types
import unittest
from unittest.mock import Mock, patch


def frame(packet):
    return b"data: " + json.dumps(packet).encode("utf-8")


class StreamTests(unittest.TestCase):
    def setUp(self):
        config = types.SimpleNamespace(API="http://unused.invalid", KEY="test-only", MODEL="test-model", THRESH=5, COOL=60, MAX_CHARS=8000)
        self.requests = types.SimpleNamespace(post=Mock(), HTTPError=type("HTTPError", (Exception,), {}))
        modules = {
            "config": config, "requests": self.requests,
            "file_tools": types.SimpleNamespace(TOOLS=[]),
            "terminal": types.SimpleNamespace(poll_control=lambda: None),
        }
        path = pathlib.Path(__file__).resolve().parents[1] / "api_client.py"
        spec = importlib.util.spec_from_file_location("stream_test_api", path)
        self.api = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", modules):
            spec.loader.exec_module(self.api)
        self.output = io.StringIO()
        capture = patch("sys.stdout", self.output)
        capture.start()
        self.addCleanup(capture.stop)

    def feed(self, packets):
        def lines(messages):
            try:
                for packet in packets:
                    yield packet if isinstance(packet, bytes) else frame(packet)
            finally:
                self.closed = True
        self.closed = False
        self.api.network_lines = Mock(side_effect=lines)

    def test_stream_error_retains_code_and_balance_message_without_appending_history(self):
        self.feed([{"error": {"message": "Insufficient Balance"}, "code": 402}])
        messages = [{"role": "user", "content": "task"}]
        with self.assertRaisesRegex(RuntimeError, r"API stream error:.*Insufficient Balance.*402"):
            self.api.stream(messages)
        self.assertEqual(messages, [{"role": "user", "content": "task"}])
        self.assertEqual(self.api.FAILS, 1)
        self.assertTrue(self.closed)

    def test_error_after_partial_tool_call_does_not_return_or_append_the_call(self):
        self.feed([
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "partial", "function": {"name": "run_cmd", "arguments": '{"command":"echo test"}'}}]}}]},
            {"error": {"message": "provider failed", "code": 500}},
        ])
        messages = []
        with self.assertRaisesRegex(RuntimeError, "provider failed"):
            self.api.stream(messages)
        self.assertEqual(messages, [])
        self.assertTrue(self.closed)

    def test_usage_and_finish_frames_do_not_break_text_or_split_tool_arguments(self):
        self.feed([
            {"choices": [{"delta": {"content": "hello "}}]},
            {"choices": [], "usage": {"prompt_tokens": 10}},
            {"choices": [{"delta": {"content": "world", "tool_calls": [{"index": 0, "id": "call-1", "function": {"name": "read_file", "arguments": '{"path":'}}]}}]},
            {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"a.txt"}'}}]}}]},
            {"choices": [{"finish_reason": "tool_calls"}]},
            b"data: [DONE]",
        ])
        self.api.FAILS = 2
        messages = []
        text, calls = self.api.stream(messages)
        self.assertEqual(text, "hello world")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]), {"path": "a.txt"})
        self.assertEqual(messages[-1]["tool_calls"], calls)
        self.assertEqual(self.api.FAILS, 0)
        self.assertTrue(self.closed)

    def test_stream_errors_count_toward_existing_circuit_breaker(self):
        self.feed([{"error": {"message": "failed"}}])
        for _ in range(5):
            with self.assertRaisesRegex(RuntimeError, "API stream error"):
                self.api.stream([])
        self.assertTrue(self.api.OPEN)
        self.assertGreater(self.api.UNTIL, time.time())
        with self.assertRaisesRegex(RuntimeError, "Circuit breaker open"):
            self.api.stream([])
        self.assertEqual(self.api.network_lines.call_count, 5)

    def test_http_error_retains_response_body_and_closes_response(self):
        response = types.SimpleNamespace(
            raise_for_status=Mock(side_effect=self.requests.HTTPError("402 Payment Required")),
            text='{"error":{"message":"Insufficient Balance"}}', close=Mock(),
        )
        self.requests.post.return_value = response
        with self.assertRaisesRegex(RuntimeError, r"402 Payment Required.*Insufficient Balance"):
            self.api.stream([])
        response.close.assert_called_once()
        self.assertEqual(self.api.FAILS, 1)


if __name__ == "__main__":
    unittest.main()
