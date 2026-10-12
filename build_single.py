# -*- coding: utf-8 -*-
"""从分文件源码生成独立单文件版，配置使用模板，不读取本地密钥。"""

import ast
from pathlib import Path

BUILD_ROOT = Path(__file__).resolve().parent
MODULES = ("config", "shell_tools", "file_tools", "terminal", "api_client", "context_compaction", "chat", "harness")


def standalone_source(source, omit=()):
    removed = set()
    for node in ast.walk(ast.parse(source)):
        local_import = (
            isinstance(node, ast.ImportFrom) and node.module in MODULES
            or isinstance(node, ast.Import) and any(alias.name in MODULES for alias in node.names)
        )
        if local_import or node in omit:
            if isinstance(node, ast.Import) and not all(alias.name in MODULES for alias in node.names):
                raise ValueError("Mixed local and external import needs explicit handling")
            removed.update(range(node.lineno, node.end_lineno + 1))
    return "\n".join(line for number, line in enumerate(source.splitlines(), 1) if number not in removed)


def build():
    entry = (BUILD_ROOT / "harness.py").read_text(encoding="utf-8")
    tree = ast.parse(entry)
    checker = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "ensure_requests")
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
             and isinstance(node.value.func, ast.Name) and node.value.func.id == "ensure_requests"]
    header = (
        '# -*- coding: utf-8 -*-\n'
        '"""Win7 文件助手单文件版；由 build_single.py 生成，直接运行本文件。"""\n\n'
        'import sys\n'
        '# 原模块共享当前文件的状态，保持 API 停止标志与配置更新一致。\n'
        'api = config = sys.modules[__name__]\n'
    )
    sections = [header, "# ===== Configuration =====\n" + (BUILD_ROOT / "config.example.py").read_text(encoding="utf-8")]
    sections.append(ast.get_source_segment(entry, checker))
    sections.append('if __name__ == "__main__":\n    ensure_requests()\n')
    for name in MODULES[1:-1]:
        source = (BUILD_ROOT / (name + ".py")).read_text(encoding="utf-8")
        sections.append("# ===== " + name + " =====\n" + standalone_source(source))
    sections.append("# ===== Entry =====\n" + standalone_source(entry, [checker, *calls]))
    source = "\n\n".join(sections) + "\n"
    ast.parse(source, feature_version=(3, 8))
    output = BUILD_ROOT / "harness_single.py"
    output.write_text(source, encoding="utf-8")
    return output


if __name__ == "__main__":
    print(build())
