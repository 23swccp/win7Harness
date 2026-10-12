# -*- coding: utf-8 -*-
"""Win7 命令工具：CMD 与 Windows PowerShell 共用执行、停止和结果处理。"""

import os, time, base64, codecs, ctypes, subprocess, tempfile
from config import MAX_CHARS

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
