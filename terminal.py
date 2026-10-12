# -*- coding: utf-8 -*-
"""终端动作显示：固定提示使用英文，非 ASCII 内容转义后预览。"""

import json, msvcrt
from config import STOP_KEY

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
