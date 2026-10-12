# -*- coding: utf-8 -*-
"""按行分页预算、完整行续读和超长行回退测试。"""

import importlib.util
import io
import pathlib
import re
import tempfile
import types
import unittest
from unittest.mock import patch


class ReadBudgetTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory(prefix="harness-read-budget-")
        self.addCleanup(workspace.cleanup)
        self.root = pathlib.Path(workspace.name)
        config = types.SimpleNamespace(ROOT=str(self.root), MAX_CHARS=32)
        shells = types.SimpleNamespace(SHELL_TOOLS=[], run_shell=None)
        path = pathlib.Path(__file__).resolve().parents[1] / "file_tools.py"
        spec = importlib.util.spec_from_file_location("budget_file_tools", path)
        self.tools = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"config": config, "shell_tools": shells}):
            spec.loader.exec_module(self.tools)

    def read(self, content, encoding="utf-8", **args):
        (self.root / "sample.txt").write_bytes(content.encode(encoding))
        return self.tools.run("read_file", dict(path="sample.txt", encoding=encoding, **args))

    def test_pages_keep_complete_lines_without_loss_or_duplicates(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=newline):
                content = "".join("行%d%s" % (i, newline) for i in range(1, 21))
                start, collected = 1, []
                while True:
                    result = self.read(content, encoding="gbk", start_line=start)
                    body, marker, notice = result.partition("\n[More lines;")
                    self.assertLessEqual(len(body), 32)
                    self.assertTrue(body.endswith(newline))
                    collected.append(body)
                    if not marker:
                        break
                    following = int(re.search(r"start_line=(\d+)", notice).group(1))
                    self.assertGreater(following, start)
                    start = following
                expected = "".join("%d: 行%d%s" % (i, i, newline) for i in range(1, 21))
                self.assertEqual("".join(collected), expected)

    def test_end_line_is_inclusive_and_no_unnecessary_notice(self):
        self.assertEqual(self.read("a\n\nb\nc", start_line=2, end_line=3), "2: \n3: b\n")
        self.assertEqual(self.read("a\n", start_line=2), "")
        self.assertEqual(self.read("", start_line=1), "")
        self.assertEqual(self.read("last", start_line=1), "1: last")
        self.tools.MAX_CHARS = 5
        self.assertEqual(self.read("a\n", start_line=1), "1: a\n")
        self.assertEqual(self.read("a\nb\n", start_line=1, end_line=1), "1: a\n")

    def test_large_file_has_bounded_single_result(self):
        self.tools.MAX_CHARS = 8000
        content = "abcdefghij\n" * 400000
        result = self.read(content, start_line=1)
        body, marker, notice = result.partition("\n[More lines;")
        self.assertTrue(marker)
        self.assertLessEqual(len(body), 8000)
        self.assertLess(len(result), 8100)
        self.assertIn("start_line=", notice)

    def test_oversized_line_reports_exact_raw_offset(self):
        content = "first\r\n" + "中" * 10000 + "\r\nlast"
        with self.assertRaisesRegex(ValueError, "Line 2 exceeds read budget; use offset=7"):
            self.read(content, encoding="gbk", start_line=2)
        raw = self.read(content, encoding="gbk", offset=7)
        self.assertEqual(raw, "中" * 32 + "\n[More content; use offset=39 to continue]")

    def test_oversized_next_line_returns_existing_lines_first(self):
        result = self.read("small\n" + "x" * 10000, start_line=1)
        self.assertEqual(result, "1: small\n\n[More lines; continue with start_line=2]")

    def test_skipping_long_lines_is_bounded_and_handles_split_crlf(self):
        budget = self.tools.MAX_CHARS

        class BoundedReader(io.StringIO):
            def readline(self, size=-1):
                self_check = 0 < size <= budget + 1
                if not self_check:
                    raise AssertionError("unbounded readline")
                return super().readline(size)

            def read(self, size=-1):
                if size != 1:
                    raise AssertionError("unbounded read")
                return super().read(size)

        for newline in ("\n", "\r\n", "\r"):
            stream = BoundedReader("x" * 100000 + newline + "last", newline="")
            self.assertEqual(self.tools.read_lines(stream, 2, None), "2: last")
        # 第一块恰好结束在 CR，LF 应归到同一个换行中。
        stream = BoundedReader("x" * 32 + "\r\nlast", newline="")
        self.assertEqual(self.tools.read_lines(stream, 2, None), "2: last")


if __name__ == "__main__":
    unittest.main()
