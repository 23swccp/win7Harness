# -*- coding: utf-8 -*-
"""文件工具：定义模型可用的工具，并执行工作区内的文件操作。"""

import os, shutil, fnmatch, stat, codecs
from config import ROOT, MAX_CHARS
from shell_tools import SHELL_TOOLS, run_shell

TEXT_ENCODING = {
    "type": "string",
    "description": "Default utf-8. For legacy files use gbk or Windows mbcs; use the same encoding for subsequent reads and edits. Decode errors require retrying with the correct encoding.",
}

# 工具描述发送给模型，保持简短英文。
TOOLS = [
    {"type": "function", "function": {"name": n, "description": d, "parameters": p}}
    for n, d, p in [
        (
            "search_text",
            "Search literal, case-sensitive text recursively or in one file. Return path:line:text. path defaults to workspace, glob to *, encoding to utf-8.",
            {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string"},
                    "glob": {"type": "string"},
                    "encoding": TEXT_ENCODING,
                },
                "required": ["query"],
            },
        ),
        (
            "find_files",
            "Find files recursively by name, e.g. *.py or *main*. path defaults to workspace.",
            {
                "type": "object",
                "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
                "required": ["pattern"],
            },
        ),
        (
            "list_files",
            "List files and folders. path defaults to workspace; list subfolders to locate files.",
            {"type": "object", "properties": {"path": {"type": "string"}}},
        ),
        (
            "read_file",
            "Read up to %d characters plus a continuation notice. Default: raw text with zero-based offset. Alternatively use start_line/end_line (1-based, inclusive) for complete numbered lines within the same character budget. Follow start_line continuation, keeping encoding and end_line. An oversized single line reports its raw offset; retry in offset mode. Do not combine line range with offset. Line-number prefixes are metadata, not file content." % MAX_CHARS,
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                    "encoding": TEXT_ENCODING,
                },
                "required": ["path"],
            },
        ),
        (
            "write_file",
            "Write or overwrite a file. Existing bytes must decode with the chosen encoding; validate content before overwriting.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "encoding": TEXT_ENCODING},
                "required": ["path", "content"],
            },
        ),
        (
            "append_file",
            "Append text to a file.",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "encoding": TEXT_ENCODING},
                "required": ["path", "content"],
            },
        ),
        (
            "replace_in_file",
            "Replace an exact, unique text match.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old": {"type": "string"},
                    "new": {"type": "string"},
                    "encoding": TEXT_ENCODING,
                },
                "required": ["path", "old", "new"],
            },
        ),
        (
            "delete_file",
            "Delete a file or folder.",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        ),
    ]
]
TOOLS += SHELL_TOOLS

# 可能修改文件的工具，命令执行也计入单轮写操作次数。
WT = ("write_file", "append_file", "replace_in_file", "delete_file", "run_cmd", "run_powershell")


# 将路径解析为真实路径，限制访问范围为工作区。
def safe(p):
    r = os.path.realpath(ROOT)
    f = os.path.realpath(os.path.join(r, p))
    if f != r and not f.startswith(r + os.sep):
        raise ValueError("Outside workspace: " + p)
    return f


# UTF-8 文件保留 BOM；旧编码由调用者指定，不用替代字符掩盖解码错误。
def text_encoding(p, a, validate=False):
    encoding = codecs.lookup(a.get("encoding", "utf-8")).name
    if os.path.isfile(p):
        if encoding == "utf-8":
            with open(p, "rb") as f:
                if f.read(3) == codecs.BOM_UTF8:
                    encoding = "utf-8-sig"
        if validate:
            try:
                with open(p, encoding=encoding, newline="") as f:
                    while f.read(65536):
                        pass
            except UnicodeDecodeError as e:
                raise ValueError(
                    "Cannot decode existing file as %s; specify the correct encoding (e.g. gbk or mbcs). File unchanged."
                    % encoding
                ) from e
    return encoding


# 先完整检查可编码性，再打开文件，避免编码失败时原文件已被截断。
def write_text(p, content, encoding, mode="w"):
    content.encode(encoding)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, mode, encoding=encoding, newline="") as f:
        f.write(content)


# 按预算返回完整行；单行过长时提示改用字符 offset，不切断行正文。
def read_lines(f, start, end):
    parts = []
    size = offset = 0
    line_no = 1
    while True:
        line = f.readline(MAX_CHARS + 1)
        if not line:
            break
        # 防止分块跳过长行时将边界上的 CRLF 误算成两行。
        if line.endswith("\r"):
            position = f.tell()
            if f.read(1) == "\n":
                line += "\n"
            else:
                f.seek(position)
        if line_no >= start:
            numbered = "%d: %s" % (line_no, line)
            if size + len(numbered) > MAX_CHARS:
                if not parts:
                    raise ValueError("Line %d exceeds read budget; use offset=%d in raw mode" % (line_no, offset))
                return "".join(parts) + "\n[More lines; continue with start_line=%d]" % line_no
            parts.append(numbered)
            size += len(numbered)
        if line_no == end:
            break
        offset += len(line)
        if line.endswith(("\r", "\n")):
            line_no += 1
    return "".join(parts)


# 共用文件遍历逻辑；跳过目录链接和 Windows Junction。
def iter_files(p):
    if os.path.isfile(p):
        yield p
        return

    for base, dirs, files in os.walk(p, followlinks=False):
        readable_dirs = []
        for d in sorted(dirs):
            try:
                info = os.lstat(os.path.join(base, d))
            except OSError:
                continue
            if not (
                getattr(info, "st_file_attributes", 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                readable_dirs.append(d)
        dirs[:] = readable_dirs
        for name in sorted(files):
            yield os.path.join(base, name)


def run(n, a, check_control=None):
    if n in ("run_cmd", "run_powershell"):
        return run_shell(n, a, safe(a.get("cwd", ".")), check_control)
    if n == "search_text":
        p = safe(a.get("path", "."))
        query = a["query"]
        if not os.path.exists(p):
            return "Not found"
        if not query:
            return "Query must not be empty"

        pattern = a.get("glob", "*").lower()
        found = []
        skipped = []

        for candidate in iter_files(p):
            if not fnmatch.fnmatchcase(os.path.basename(candidate).lower(), pattern):
                continue
            try:
                target = safe(candidate)
                # 用文件头的零字节粗略识别二进制文件。
                with open(target, "rb") as f:
                    if b"\0" in f.read(1024):
                        continue

                # 逐行搜索，返回文件路径、从 1 开始的行号和匹配内容。
                with open(target, encoding=text_encoding(target, a)) as f:
                    for line_no, line in enumerate(f, 1):
                        if query in line:
                            found.append(
                                "%s:%d: %s"
                                % (os.path.relpath(candidate, ROOT), line_no, line.rstrip("\r\n"))
                            )
            except (OSError, ValueError, LookupError):
                skipped.append(os.path.relpath(candidate, ROOT))

        result = "\n".join(found) or "No matches"
        if skipped:
            result += "\nSkipped unreadable files: %d; check encoding (e.g. gbk or mbcs).\n" % len(skipped)
            result += "\n".join(skipped)
        return result

    if n == "find_files":
        p = safe(a.get("path", "."))
        pattern = a["pattern"].lower()
        if not os.path.isdir(p):
            return "Folder not found"
        found = []

        for candidate in iter_files(p):
            if fnmatch.fnmatchcase(os.path.basename(candidate).lower(), pattern):
                found.append(os.path.relpath(candidate, ROOT))
        return "\n".join(sorted(found)) or "No matching files"

    if n == "list_files":
        p = safe(a.get("path", "."))
        if not os.path.isdir(p):
            return "Folder not found"
        return (
            "\n".join(
                ("[DIR] " if os.path.isdir(os.path.join(p, f)) else "[FILE] ") + f
                for f in sorted(os.listdir(p))
            )
            or "Empty folder"
        )

    if n == "read_file":
        p = safe(a["path"])
        if not os.path.isfile(p):
            return "Not found"
        if "start_line" in a or "end_line" in a:
            if "offset" in a:
                raise ValueError("Use either offset or start_line/end_line")
            start, end = a.get("start_line", 1), a.get("end_line")
            if type(start) is not int or start < 1:
                raise ValueError("start_line must be a positive integer")
            if end is not None and (type(end) is not int or end < start):
                raise ValueError("end_line must be an integer >= start_line")
            with open(p, encoding=text_encoding(p, a), newline="") as f:
                return read_lines(f, start, end)
        offset = a.get("offset", 0)
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        with open(p, encoding=text_encoding(p, a), newline="") as f:
            # 字符偏移不能直接 seek；分块跳过，避免把前面的内容全部读入内存。
            remaining = offset
            while remaining:
                skipped = f.read(min(remaining, MAX_CHARS))
                if not skipped:
                    return ""
                remaining -= len(skipped)
            s = f.read(MAX_CHARS + 1)
        if len(s) > MAX_CHARS:
            return s[:MAX_CHARS] + "\n[More content; use offset=%d to continue]" % (offset + MAX_CHARS)
        return s

    # 覆盖与追加共用实现，只切换文件打开模式。
    if n in ("write_file", "append_file"):
        p = safe(a["path"])
        encoding = text_encoding(p, a, validate=True)
        write_text(p, a["content"], encoding, "w" if n == "write_file" else "a")
        return "Written" if n == "write_file" else "Appended"

    if n == "replace_in_file":
        p = safe(a["path"])
        encoding = text_encoding(p, a)
        with open(p, encoding=encoding, newline="") as f:
            t = f.read()
        c = t.count(a["old"])
        if c == 0:
            return "Text not found"
        if c > 1:
            return "Found %d matches; expected one" % c

        write_text(p, t.replace(a["old"], a["new"], 1), encoding)
        return "Replaced"

    if n == "delete_file":
        p = safe(a["path"])
        if p == os.path.realpath(ROOT):
            raise ValueError("Refusing to delete the workspace root")
        if not os.path.exists(p):
            return "Not found"
        os.remove(p) if os.path.isfile(p) else shutil.rmtree(p)
        return "Deleted"

    return "Unknown tool"
