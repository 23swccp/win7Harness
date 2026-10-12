# -*- coding: utf-8 -*-
"""Python 入口依赖检查测试；不执行真实 pip 安装。"""

import importlib.util
import io
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


class StartupTests(unittest.TestCase):
    def setUp(self):
        path = pathlib.Path(__file__).resolve().parents[1] / "harness.py"
        spec = importlib.util.spec_from_file_location("test_harness_entry", path)
        self.entry = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"config": types.SimpleNamespace()}):
            spec.loader.exec_module(self.entry)
        capture = patch("sys.stdout", io.StringIO())
        capture.start()
        self.addCleanup(capture.stop)

    def test_valid_dependency_starts_without_pip(self):
        with patch("subprocess.call", return_value=0) as call:
            self.entry.ensure_requests()
        call.assert_called_once()
        self.assertEqual(call.call_args.args[0][:2], [sys.executable, "-c"])

    def test_missing_dependency_installs_using_same_interpreter_then_rechecks(self):
        with patch("subprocess.call", side_effect=[1, 0, 0, 0]) as call:
            self.entry.ensure_requests()
        commands = [item.args[0] for item in call.call_args_list]
        self.assertTrue(all(command[0] == sys.executable for command in commands))
        self.assertEqual(commands[2], [sys.executable, "-m", "pip", "install", "--upgrade", "requests>=2.32.4,<3"])
        self.assertEqual(commands[-1], commands[0])

    def test_missing_pip_is_bootstrapped(self):
        with patch("subprocess.call", side_effect=[1, 1, 0, 0, 0]) as call:
            self.entry.ensure_requests()
        self.assertEqual(call.call_args_list[2].args[0], [sys.executable, "-m", "ensurepip", "--upgrade"])

    def test_installation_failures_stop_startup(self):
        cases = (([1, 1, 1], "Failed to prepare pip"),
                 ([1, 0, 1], "Requests installation failed"),
                 ([1, 0, 0, 1], "still unavailable or incompatible"))
        for results, message in cases:
            with self.subTest(message=message), patch("subprocess.call", side_effect=results):
                with self.assertRaisesRegex(SystemExit, message):
                    self.entry.ensure_requests()

    def test_old_python_stops_before_dependency_install(self):
        with patch.object(self.entry.sys, "version_info", (3, 7)), patch("subprocess.call") as call:
            with self.assertRaisesRegex(SystemExit, "Python 3.8"):
                self.entry.ensure_requests()
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
