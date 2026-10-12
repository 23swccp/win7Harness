# -*- coding: utf-8 -*-
"""Win7 文件助手单文件版；由 build_single.py 生成，直接运行本文件。"""

import sys
# 原模块共享当前文件的状态，保持 API 停止标志与配置更新一致。
api = config = sys.modules[__name__]


# ===== Configuration =====
# -*- coding: utf-8 -*-
"""公共配置：API、模型、工作目录和操作限制。"""

import os

# API 请求地址与密钥；URL、密钥或模型名留空时，启动会提示补填。
API = ""
KEY = ""  # 启动补填时隐藏输入；不要提交含密钥的 config.py。

# 以启动时所在目录作为工作区。
ROOT = os.getcwd()

# 模型名；也可留空，在启动时输入。
MODEL = "deepseek-v4-flash"

# 工具结果与文件读取的字符上限；按行读取包含行号，续读提示另附。
MAX_CHARS = 8000

# 单轮任务允许的写操作尝试次数，包括修改和删除。
MAX_WRITES = 10

# 上下文预算须不大于实际模型容量；0 关闭自动压缩，仍可 /compact。
CONTEXT_TOKENS = 128000
# 压缩时保留最近约这么多估算 token，当前整轮始终保留。
KEEP_TOKENS = 15000
# 摘要请求的输出 token 上限。
SUMMARY_TOKENS = 4096

# Esc 用于叫停当前轮次。
STOP_KEY = b"\x1b"

# 连续失败达到阈值后熔断，冷却时间单位为秒。
THRESH = 5
COOL = 60


def ensure_requests():
    """使用当前解释器检查与安装依赖，不在父进程加载待升级的旧库。"""
    import subprocess

    if sys.version_info < (3, 8):
        raise SystemExit("Python 3.8 or newer is required.")
    check = [sys.executable, "-c", "import sys, requests; v = tuple(map(int, requests.__version__.split('.'))); sys.exit(not ((2, 32, 4) <= v < (3,)))"]
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if subprocess.call(check, **quiet) == 0:
        return
    print("Installing a compatible Requests version...", flush=True)
    pip = [sys.executable, "-m", "pip"]
    if subprocess.call(pip + ["--version"], **quiet) != 0:
        if subprocess.call([sys.executable, "-m", "ensurepip", "--upgrade"]) != 0:
            raise SystemExit("Failed to prepare pip. Install pip for this Python and try again.")
    if subprocess.call(pip + ["install", "--upgrade", "requests>=2.32.4,<3"]) != 0:
        raise SystemExit("Requests installation failed. Check network access and pip.")
    if subprocess.call(check, **quiet) != 0:
        raise SystemExit("Requests is still unavailable or incompatible after installation.")

if __name__ == "__main__":
    ensure_requests()


# ===== shell_tools =====
# -*- coding: utf-8 -*-
"""Win7 命令工具：CMD 与 Windows PowerShell 共用执行、停止和结果处理。"""

import os, time, base64, codecs, ctypes, subprocess, tempfile

PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {"type": "string"},
        "cwd": {"type": "string", "description": "Working directory within workspace; default workspace root."},
        "timeout": {"type": "integer", "minimum": 1, "description": "Timeout in seconds; default 60."},
        "encoding": {"type": "string", "description": "Output encoding override; CMD defaults to system OEM code page, PowerShell to utf-8."},
    },
    "required": ["command"],
}

SHELL_TOOLS = [
    {"type": "function", "function": {"name": name, "description": description, "parameters": PARAMETERS}}
    for name, description in (
        ("run_cmd", "Run a non-interactive Windows 7 CMD command, not Bash. Return exit code and combined stdout/stderr. Each call starts a fresh process; cwd/env changes do not persist. Prefer file tools for edits preserving encoding."),
        ("run_powershell", "Run a non-interactive Windows PowerShell command using PowerShell 2.0-compatible syntax, not Bash or PowerShell 7 syntax. Return exit code and combined stdout/stderr. Each call starts a fresh process; variables/cwd do not persist. Prefer file tools for edits preserving encoding."),
    )
]


# 超时或用户停止时，结束命令及其子进程。
def stop_process(process, system32):
    try:
        subprocess.run(
            [os.path.join(system32, "taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        process.kill()
    process.wait()


def run_shell(name, args, cwd, check_control=None):
    command = args["command"]
    timeout = args.get("timeout", 60)
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must be a non-empty string")
    if type(timeout) is not int or timeout < 1:
        raise ValueError("timeout must be a positive integer")
    if not os.path.isdir(cwd):
        raise ValueError("Working directory not found")
    system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    if name == "run_cmd":
        exe = os.path.join(system32, "cmd.exe")
        # CMD /S 只去掉最外层引号，内部命令不经 list2cmdline 再次转义。
        argv = '"%s" /D /S /C "%s"' % (exe, command)
        encoding = args.get("encoding", "cp%d" % ctypes.windll.kernel32.GetOEMCP())
    else:
        exe = os.path.join(system32, "WindowsPowerShell", "v1.0", "powershell.exe")
        # EncodedCommand 使用 UTF-16LE；脚本只用 PowerShell 2.0 支持的语法。
        script = (
            "$OutputEncoding = New-Object System.Text.UTF8Encoding\n"
            "[Console]::OutputEncoding = $OutputEncoding\n"
            "$ErrorActionPreference = 'Stop'\n$LASTEXITCODE = $null\ntry {\n"
            + command
            + "\nif ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }\n"
            "} catch { [Console]::Error.WriteLine($_.ToString()); exit 1 }\n"
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        argv = [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-OutputFormat", "Text", "-EncodedCommand", encoded]
        encoding = args.get("encoding", "utf-8")
    codecs.lookup(encoding)
    if check_control and check_control():
        return "Stopped before execution"

    # 临时文件接收输出，避免管道填满阻塞，也不将无限输出全部放进内存。
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        deadline = time.monotonic() + timeout
        status = "Completed"
        try:
            while process.poll() is None:
                if check_control and check_control():
                    status = "Stopped"
                    break
                if time.monotonic() >= deadline:
                    status = "Timed out after %d seconds" % timeout
                    break
                try:
                    process.wait(timeout=0.05)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if process.poll() is None:
                stop_process(process, system32)
        output.seek(0)
        text = output.read(MAX_CHARS * 4 + 4).decode(encoding, errors="backslashreplace")
    return "%s\nExit code: %d\n%s" % (status, process.returncode, text)

# ===== file_tools =====
# -*- coding: utf-8 -*-
"""文件工具：定义模型可用的工具，并执行工作区内的文件操作。"""

import os, shutil, fnmatch, stat, codecs

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

# ===== terminal =====
# -*- coding: utf-8 -*-
"""终端动作显示：固定提示使用英文，非 ASCII 内容转义后预览。"""

import json, msvcrt

_command = ""


# 任务刚结束时，保留已经输入的命令前缀，避免把剩余字符发给模型。
def read_prompt():
    global _command

    prefix = _command
    _command = ""
    return prefix + input("\nYou> " + prefix)


# 工作期间只接收控制命令；普通任务仍在 You> 提示下输入。
def poll_control():
    global _command

    while msvcrt.kbhit():
        ch = msvcrt.getwch()
        if ch in ("\0", "\xe0"):
            msvcrt.getwch()
            continue

        if ch == STOP_KEY.decode("ascii"):
            _command = ""
            return "/quit"

        if not _command:
            if ch == "/":
                _command = "/"
                print("\nCommand> /", end="", flush=True)
            continue

        if ch in ("\r", "\n"):
            command = _command.lower()
            _command = ""
            print()
            if command in ("/quit", "/exit"):
                return command
            print("Unknown command. Use /quit or /exit.", flush=True)
        elif ch == "\b":
            _command = _command[:-1]
            print("\b \b", end="", flush=True)
        elif ch.isascii() and ch.isprintable() and len(_command) < 32:
            _command += ch
            print(ch, end="", flush=True)


# 只处理终端预览，不改变文件正文或交给模型的工具结果。
def preview(text, limit=160):
    text = str(text).encode("ascii", "backslashreplace").decode("ascii")
    return text[:limit] + "..." if len(text) > limit else text


def show_action(number, name, args):
    fields = []
    for key in ("path", "cwd", "command", "timeout", "offset", "start_line", "end_line", "pattern", "query", "glob", "encoding"):
        if key in args:
            fields.append(key + "=" + preview(json.dumps(args[key], ensure_ascii=True)))

    # 写入及替换内容只显示长度，避免刷屏。
    for key in ("content", "old", "new"):
        if key in args:
            fields.append("%s=%d chars" % (key, len(str(args[key]))))

    print("\nTool %d> %s %s" % (number, preview(name), " ".join(fields)), flush=True)


# 读取文件时显示字符数；其他结果最多预览前三行。
def show_result(name, result):
    errors = ("Failed:", "Invalid arguments:", "Not found")
    if name == "read_file" and not result.startswith(errors):
        print("  -> Read %d chars" % len(result), flush=True)
        return

    lines = result.splitlines()
    if not lines:
        lines = ["(empty)"]
    for line in lines[:3]:
        print("  -> " + preview(line), flush=True)
    if len(lines) > 3:
        print("  -> ... (%d more lines)" % (len(lines) - 3), flush=True)

# ===== api_client =====
# -*- coding: utf-8 -*-
"""网络调用：流式输出、Esc 停止检查和连续失败熔断。"""

import sys, json, time, copy, queue, threading, requests

# 网络状态由本模块维护，聊天模块通过 api.STOP 读取停止标志。
FAILS = 0
OPEN = False
UNTIL = 0.0
STOP = False
EXIT = False


def check_control():
    global STOP, EXIT

    command = poll_control()
    if command:
        STOP = True
        EXIT = command == "/exit"
        print("\n[Exiting]" if EXIT else "\n[Stopped]", flush=True)

    return STOP


# 网络在后台读取；主线程每 0.05 秒检查命令，连接等待时也能返回输入提示。
def network_lines(msgs, with_tools=True, max_tokens=None):
    if OPEN and time.time() < UNTIL:
        raise RuntimeError("Circuit breaker open")
    packets = queue.Queue(maxsize=16)
    cancelled = threading.Event()
    payload = {"model": MODEL, "messages": copy.deepcopy(msgs), "stream": True}
    if with_tools:
        payload["tools"] = TOOLS
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    headers = {"Authorization": "Bearer " + KEY}

    def put(kind, value=None):
        while not cancelled.is_set():
            try:
                packets.put((kind, value), timeout=0.05)
                return
            except queue.Full:
                pass

    def read():
        r = None

        try:
            r = requests.post(API, headers=headers, json=payload, timeout=(5, 60), stream=True)
            try:
                r.raise_for_status()
            except requests.HTTPError as e:
                raise RuntimeError("API HTTP error: %s; %s" % (e, r.text[:MAX_CHARS])) from e
            if cancelled.is_set():
                return

            for line in r.iter_lines(chunk_size=1):
                if cancelled.is_set():
                    break
                put("line", line)
        except Exception as e:
            put("error", e)
        finally:
            if r is not None:
                try:
                    r.close()
                except Exception:
                    pass
            put("done")

    threading.Thread(target=read, daemon=True).start()
    try:
        while not check_control():
            try:
                kind, value = packets.get(timeout=0.05)
            except queue.Empty:
                continue
            if kind == "error":
                raise value
            if kind == "done":
                return
            yield value
    finally:
        # 取消后的响应不再显示或执行；后台读取结束后关闭连接。
        cancelled.set()


def stream(msgs):
    global FAILS, OPEN, UNTIL, STOP

    STOP = False
    if OPEN:
        if time.time() < UNTIL:
            raise RuntimeError("Circuit breaker open")
        OPEN = False
        FAILS = 0

    lines = network_lines(msgs)
    content = ""
    buf = {}

    try:
        for line in lines:
            if not line or not line.startswith(b"data:"):
                continue
            pl = line[5:].strip()
            if pl == b"[DONE]":
                break

            packet = json.loads(pl)
            if packet.get("error"):
                raise RuntimeError("API stream error: %s" % json.dumps(packet, ensure_ascii=False))
            choices = packet.get("choices") or []
            if not choices:
                continue
            d = choices[0].get("delta") or {}
            if d.get("content"):
                content += d["content"]
                sys.stdout.write(d["content"])
                sys.stdout.flush()

            # 同一个工具调用的参数可能分多段到达，按索引拼接。
            for tc in d.get("tool_calls") or []:
                i = tc.get("index", 0)
                s = buf.setdefault(i, {"id": "", "name": "", "args": ""})
                if tc.get("id"):
                    s["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    s["name"] = fn["name"]
                if fn.get("arguments"):
                    s["args"] += fn["arguments"]
        FAILS = 0
    except Exception:
        FAILS += 1
        if FAILS >= THRESH and not OPEN:
            OPEN = True
            UNTIL = time.time() + COOL
            print("\n[Circuit open] %d failures; wait %d seconds" % (FAILS, COOL))
        raise
    finally:
        lines.close()

    # 只将能解析为 JSON 的工具参数交给聊天循环。
    tcs = []
    for i in sorted(buf):
        s = buf[i]
        if not s["id"] or not s["name"]:
            continue
        try:
            json.loads(s["args"] or "{}")
        except:
            continue
        tcs.append(
            {
                "id": s["id"],
                "type": "function",
                "function": {"name": s["name"], "arguments": s["args"] or "{}"},
            }
        )
    m = {"role": "assistant", "content": content or None}
    if tcs:
        m["tool_calls"] = tcs
    msgs.append(m)
    return content, tcs

# ===== context_compaction =====
# -*- coding: utf-8 -*-
"""移植 OpenCode 的滚动摘要提示词，适配本项目的消息列表与流式 API。"""

# Prompt source: https://github.com/anomalyco/opencode/blob/773d8621d6bcd311067b225d837c917b3e83573e/packages/core/src/session/compaction.ts
# MIT License
#
# Copyright (c) 2025 opencode
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import json

# 以下模板和规则原样取自上述固定版本；其余代码仅负责 Python 接入。
SUMMARY_TEMPLATE = """You MUST use this format for your response (you may omit sections that aren't applicable). Do not include the <template> tags in your response.
<template>
## Objective
- [one or two brief sentences describing what the user is trying to accomplish]

## Requirements
- [constraints, preferences, requirements, and scope boundaries stated by the user, or "(none)"]

## Decisions
- [decisions already made and why, or "(none)"]

## Work State
Break the objective into smaller goals and report which are completed, which are being worked on, and which are blocked.
### Completed
- [goals that have been completed; otherwise "(none)"]

### Active
- [goals currently being worked on; otherwise "(none)"]

### Blocked
- [anything blocking progress, and why; otherwise "(none)"]

## Next Move
1. [ordered list of next actions, or "(none)"]

## Relevant Files
List the files and directories, other than the current working directory, that another agent would need to open to continue this work. Include at most 15, most important first. Do not list every file that was read or changed. Include paths outside the current working directory when relevant. If none, write "(none)".
- `[file or directory path]`: [brief reason it matters]

## Important Context
- [facts the next agent cannot continue without and cannot easily find on its own; or "(none)"]
</template>"""

SUMMARY_RULES = """Rules:
- Keep each section concise. Use terse, single-line bullets, not prose paragraphs or nested lists.
- Prefer short references over detailed restatement. It is fine to leave out information the next agent can recover from the code or the files listed above.
- Preserve exact file paths, symbols, commands, error strings, URLs, and identifiers.
- Carry forward only user questions or requests that remain unanswered or require further action. Do not repeat ones that newer history has answered or resolved. Preserve exact wording when carrying one forward.
- Preserve consequential workflow state, including whether changes are uncommitted, committed, pushed, under review, or merged.
- Do not mention the summary process or that context was compacted."""


def build_prompt(update):
    shared = [
        "Summarize only what the user and the assistant said and did. Leave out instructions and setup the assistant was given rather than told by the user: repository conventions, instruction files such as AGENTS.md, and environment details like the session ID. The next agent receives current versions of all of these separately.",
        SUMMARY_TEMPLATE, SUMMARY_RULES,
        "Do not continue the task or call tools.",
        "Return only the structured summary in the requested format. Do not include a preamble, explanation, or other commentary.",
    ]
    if not update:
        return "\n\n".join([
            "You MUST summarize the conversation above into a structured summary that will be given to another agent to resume the work.",
            *shared,
        ])
    return "\n\n".join([
        "Update the existing checkpoint in the conversation above into one consolidated summary.",
        "Newer history always takes precedence over the existing checkpoint. Preserve previous information unless newer history clearly contradicts, supersedes, resolves, or makes it stale. If something is no longer relevant to continuing the work, you may remove it.",
        "Incorporate newer requirements, decisions, progress, and context. Reconcile Work State and Next Move: move completed work out of Active, remove resolved blockers and answered questions, and preserve unresolved or pending work.",
        "Return only the updated Markdown sections. Do not reproduce the `<conversation-checkpoint>`, `<summary>`, or `<recent-context>` wrapper tags from the previous checkpoint.",
        *shared,
    ])


# 无额外 tokenizer 依赖；按 UTF-8 字节粗估，中文比字符数 / 4 更保守。
def estimate(value):
    return (len(json.dumps(value, ensure_ascii=False).encode("utf-8")) + 2) // 3


def summarize(history, update, max_tokens):
    request = [
        {"role": "system", "content": build_prompt(update)},
        {"role": "user", "content": json.dumps(history, ensure_ascii=False)},
    ]
    text, finish = "", None
    lines = api.network_lines(request, with_tools=False, max_tokens=max_tokens)
    try:
        for line in lines:
            if not line or not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                break
            packet = json.loads(payload)
            if packet.get("error"):
                raise ValueError("Summary API error: %s" % packet["error"])
            for choice in packet.get("choices") or []:
                delta = choice.get("delta") or {}
                if delta.get("tool_calls"):
                    raise ValueError("Summary attempted a tool call")
                text += delta.get("content") or ""
                if choice.get("finish_reason") is not None:
                    finish = choice["finish_reason"]
    finally:
        lines.close()
    if api.STOP:
        return None
    headings = {line for line in SUMMARY_TEMPLATE.splitlines() if line.startswith("## ")}
    if finish != "stop" or not any(line.strip() in headings for line in text.splitlines()):
        raise ValueError("Summary incomplete or missing the required template")
    return text.strip()


class ContextCompactor:
    def __init__(self):
        self.window = getattr(config, "CONTEXT_TOKENS", 128000)
        self.keep = getattr(config, "KEEP_TOKENS", 15000)
        self.max_summary = getattr(config, "SUMMARY_TOKENS", 4096)
        if type(self.window) is not int or self.window < 0:
            raise ValueError("CONTEXT_TOKENS must be a non-negative integer")
        if any(type(value) is not int or value < 1 for value in (self.keep, self.max_summary)):
            raise ValueError("KEEP_TOKENS and SUMMARY_TOKENS must be positive integers")
        self.summary = ""
        self.failed = False

    def compact(self, messages, force=False):
        if force:
            self.failed = False
        if not force and (not self.window or self.failed):
            return False
        before = estimate(messages) + estimate(TOOLS)
        reserve = max(self.window // 10, 16000 if self.window >= 32000 else 0, self.max_summary)
        if not force and before < self.window - reserve:
            return False

        # 摘要位于系统提示后；按用户消息划分整轮，始终保留当前轮。
        first = 2 if self.summary else 1
        boundaries = [i for i in range(first, len(messages)) if messages[i]["role"] == "user"]
        if len(boundaries) < 2:
            return False
        cut = boundaries[-1]
        recent_size = estimate(messages[cut:])
        for index in reversed(boundaries[:-1]):
            size = estimate(messages[index:cut])
            if recent_size + size > self.keep:
                break
            recent_size += size
            cut = index
        if cut == first:
            cut = boundaries[-1]
        history = messages[1:cut]
        print("\n[Compacting context]", flush=True)
        try:
            summary = summarize(history, bool(self.summary), self.max_summary)
            if summary is None or api.check_control():
                return False
            checkpoint = {
                "role": "user",
                "content": "<conversation-checkpoint>\n<summary>\n" + summary + "\n</summary>\n</conversation-checkpoint>",
            }
            candidate = [messages[0], checkpoint] + messages[cut:]
            after = estimate(candidate) + estimate(TOOLS)
            if after >= before:
                raise ValueError("Summary did not reduce context size")
        except KeyboardInterrupt:
            api.STOP = True
            return False
        except Exception as e:
            self.failed = True
            print("[Compaction failed; history kept] %s" % e, flush=True)
            return False
        messages[:] = candidate
        self.summary = summary
        self.failed = False
        print("[Context compacted] estimated tokens: %d -> %d" % (before, after), flush=True)
        return True

# ===== chat =====
# -*- coding: utf-8 -*-
"""聊天与工具循环：接收任务、执行模型请求的动作，再将结果交回模型。"""

import json

WRITES = 0


def main():
    global WRITES

    # 按上下文预算压缩历史，保留滚动摘要和最近整轮对话。
    compactor = ContextCompactor()
    msgs = [
        {
            "role": "system",
            "content": "You are a file and shell assistant. Workspace: "
            + ROOT
            + ". Handle files carefully. Reply in the user's language. "
            "run_cmd and run_powershell execute with the current user's permissions and are not confined to the workspace. "
            "You must not modify or delete files outside the workspace, or use shell commands to bypass file-tool path checks or write limits. "
            "Prefer file tools for file edits to preserve encoding.",
        }
    ]
    print("Workspace:", ROOT)
    print("Commands: /compact summarizes history; /quit stops the task; /exit exits. Esc also stops.")

    while True:
        try:
            u = read_prompt().strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not u:
            continue
        if u.lower() in ("/exit", "exit", "quit"):
            break
        if u.lower() == "/quit":
            print("[No task is running]")
            continue
        if u.lower() == "/compact":
            api.STOP = False
            if not compactor.compact(msgs, force=True) and not api.STOP and not compactor.failed:
                print("[No older conversation to compact]")
            if api.EXIT:
                break
            api.STOP = False
            continue
        if u.startswith("/"):
            print("Unknown command. Use /compact, /quit or /exit.")
            continue

        msgs.append({"role": "user", "content": u})
        # 记录本轮追加位置；中断时丢弃后续消息，不撤销文件修改。
        snap = len(msgs)
        WRITES = 0
        api.STOP = False
        compactor.failed = False
        action_no = 0

        try:
            # 持续调用模型，直到没有工具调用或用户主动中断。
            while True:
                if api.check_control():
                    break

                previous_length = len(msgs)
                if compactor.compact(msgs):
                    # 压缩改变历史长度，更新本轮中断时的回滚位置。
                    snap -= previous_length - len(msgs)
                if api.STOP:
                    break
                print("\nAssistant> ", end="", flush=True)
                _, tcs = api.stream(msgs)
                print()
                if api.STOP or not tcs:
                    break

                for tc in tcs:
                    if api.check_control():
                        break
                    n = tc["function"]["name"]
                    action_no += 1

                    try:
                        a = json.loads(tc["function"]["arguments"] or "{}")
                        if not isinstance(a, dict):
                            raise ValueError("Expected an object")
                    except Exception as e:
                        res = "Invalid arguments: %s" % e
                        show_action(action_no, n, {})
                        show_result(n, res)
                        msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": res})
                        continue

                    # 动作先显示，再执行；结果预览只用于终端。
                    show_action(action_no, n, a)
                    if n in WT:
                        if WRITES >= MAX_WRITES:
                            show_result(n, "Write limit reached")
                            msgs.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc["id"],
                                    "content": "Write limit reached",
                                }
                            )
                            continue
                        WRITES += 1

                    try:
                        res = run(n, a, api.check_control)
                    except Exception as e:
                        res = "Failed: %s" % e
                    res = str(res)
                    show_result(n, res)

                    # read_file 按自身参数控制读取范围；其他结果在此截断。
                    if n != "read_file" and len(res) > MAX_CHARS:
                        res = res[:MAX_CHARS] + "...[truncated]"

                    # 用调用 ID 关联结果，供下一次模型请求使用。
                    msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": res})
                    if api.STOP:
                        break
                if api.STOP:
                    break

            if api.STOP:
                del msgs[snap:]
                print("[Turn discarded]")
                api.STOP = False
            if api.EXIT:
                break
        except KeyboardInterrupt:
            del msgs[snap:]
            api.STOP = False
            print("\n[Interrupted; turn discarded]")
        except Exception as e:
            del msgs[snap:]
            api.STOP = False
            print("\n[Error]", e)

    print("Bye")

# ===== Entry =====
# -*- coding: utf-8 -*-
"""启动入口：在命令行运行 python harness.py。"""

import sys
from getpass import getpass


def ensure_requests():
    """使用当前解释器检查与安装依赖，不在父进程加载待升级的旧库。"""
    import subprocess

    if sys.version_info < (3, 8):
        raise SystemExit("Python 3.8 or newer is required.")
    check = [sys.executable, "-c", "import sys, requests; v = tuple(map(int, requests.__version__.split('.'))); sys.exit(not ((2, 32, 4) <= v < (3,)))"]
    quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if subprocess.call(check, **quiet) == 0:
        return
    print("Installing a compatible Requests version...", flush=True)
    pip = [sys.executable, "-m", "pip"]
    if subprocess.call(pip + ["--version"], **quiet) != 0:
        if subprocess.call([sys.executable, "-m", "ensurepip", "--upgrade"]) != 0:
            raise SystemExit("Failed to prepare pip. Install pip for this Python and try again.")
    if subprocess.call(pip + ["install", "--upgrade", "requests>=2.32.4,<3"]) != 0:
        raise SystemExit("Requests installation failed. Check network access and pip.")
    if subprocess.call(check, **quiet) != 0:
        raise SystemExit("Requests is still unavailable or incompatible after installation.")


if __name__ == "__main__":
    sys.stdout.reconfigure(errors="backslashreplace")
    ensure_requests()
    # 只补填缺失配置；先完成输入，再加载使用配置的聊天与网络模块。
    try:
        for name, label in (("API", "API URL"), ("KEY", "API key"), ("MODEL", "Model name")):
            value = (getattr(config, name, "") or "").strip()
            reader = getpass if name == "KEY" and sys.stdin.isatty() else input
            while not value:
                value = reader(label + ": ").strip()
            setattr(config, name, value)
    except (EOFError, KeyboardInterrupt):
        print("\nBye")
        sys.exit(0)
    main()
