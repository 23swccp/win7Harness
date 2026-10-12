# -*- coding: utf-8 -*-
"""单文件产物的独立启动与文件、流、压缩状态测试，不访问付费 API。"""

import ast
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

PROJECT = pathlib.Path(__file__).resolve().parents[1]


class SingleBuildTests(unittest.TestCase):
    def test_generated_file_matches_sources_and_has_no_project_imports(self):
        spec = importlib.util.spec_from_file_location("test_single_builder", PROJECT / "build_single.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        previous = (PROJECT / "harness_single.py").read_text(encoding="utf-8")
        result = builder.build().read_text(encoding="utf-8")
        self.assertEqual(result, previous)
        tree = ast.parse(result, feature_version=(3, 8))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn(node.module, builder.MODULES)
            if isinstance(node, ast.Import):
                self.assertTrue(all(alias.name not in builder.MODULES for alias in node.names))
        self.assertIn("Copyright (c) 2025 opencode", result)


@unittest.skipUnless(os.name == "nt", "Windows-only terminal tools")
class SingleRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="harness single file ")
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        self.tool = self.root / "tool"
        self.workspace = self.root / "workspace"
        self.stubs = self.root / "dependencies"
        for path in (self.tool, self.workspace, self.stubs):
            path.mkdir()
        self.entry = self.tool / "harness_single.py"
        self.entry.write_bytes((PROJECT / "harness_single.py").read_bytes())
        (self.stubs / "requests.py").write_text(
            "__version__ = '2.32.4'\nclass HTTPError(Exception): pass\n"
            "def post(*args, **kwargs): raise AssertionError('External API call forbidden in tests')\n",
            encoding="utf-8",
        )
        self.environment = os.environ.copy()
        self.environment["PYTHONPATH"] = str(self.stubs)

    def test_standalone_starts_with_redirected_config_and_no_companion_files(self):
        result = subprocess.run([sys.executable, str(self.entry)], cwd=self.workspace, env=self.environment,
                                input="http://unused.invalid\nstub-key\n", capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Workspace: " + str(self.workspace), result.stdout)
        self.assertIn("You>", result.stdout)
        self.assertNotIn("stub-key", result.stdout)
        self.assertEqual(list(self.tool.iterdir()), [self.entry])

    def test_file_stream_and_compaction_share_correct_state_in_single_file(self):
        script = r'''
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import harness_single as tool
assert tool.api is tool.config is tool
assert tool.ROOT == str(pathlib.Path.cwd())
tool.run('write_file', {'path': 'legacy.txt', 'content': '\u4e2d\u6587', 'encoding': 'gbk'})
assert tool.run('read_file', {'path': 'legacy.txt', 'encoding': 'gbk'}) == '\u4e2d\u6587'
assert {'run_cmd', 'run_powershell'} <= {item['function']['name'] for item in tool.TOOLS}
def response(packet):
    yield b'data: ' + json.dumps(packet).encode()
    yield b'data: [DONE]'
tool.check_control = lambda: tool.STOP
tool.network_lines = lambda *a, **k: response({'error': {'message': 'Insufficient Balance', 'code': 402}})
try:
    tool.stream([])
except RuntimeError as e:
    assert 'Insufficient Balance' in str(e)
else:
    raise AssertionError('stream error was ignored')
assert tool.FAILS == 1
tool.network_lines = lambda *a, **k: response({'choices': [{'delta': {'content': '## Objective\n- Continue.\n## Requirements\n- Keep GBK.'}, 'finish_reason': 'stop'}]})
messages = [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'old task ' * 3000}, {'role': 'assistant', 'content': 'done'}, {'role': 'user', 'content': 'current task'}]
compactor = tool.ContextCompactor()
assert compactor.compact(messages, force=True)
assert '<conversation-checkpoint>' in messages[1]['content']
assert messages[-1]['content'] == 'current task'
print('PASS: standalone file tools, stream errors, and compaction state')
'''
        result = subprocess.run([sys.executable, "-c", script, str(self.tool)], cwd=self.workspace, env=self.environment,
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("PASS: standalone", result.stdout)


if __name__ == "__main__":
    unittest.main()
