# -*- coding: utf-8 -*-
"""聊天与工具循环：接收任务、执行模型请求的动作，再将结果交回模型。"""

import json
import os
import tempfile
import config
import api_client as api
from config import ROOT, MAX_CHARS
from file_tools import run
from terminal import read_prompt, show_action, show_result
from context_compaction import ContextCompactor



def load_context(path, system, compactor):
    """恢复历史；系统提示始终使用当前版本。"""
    if not os.path.exists(path):
        return [system]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("messages"), list) or not isinstance(data.get("summary"), str):
        raise ValueError("Invalid context file")
    messages = data["messages"]
    if any(not isinstance(m, dict) or m.get("role") not in ("user", "assistant", "tool") for m in messages):
        raise ValueError("Invalid context messages")
    compactor.summary = data["summary"]
    return [system] + messages


def save_context(path, messages, compactor):
    """原子替换，避免中途退出损坏上次保存的历史。"""
    directory = os.path.dirname(os.path.abspath(path))
    fd, temporary = tempfile.mkstemp(prefix=".win7harness-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "summary": compactor.summary, "messages": messages[1:]}, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def main():
    # 按上下文预算压缩历史，保留滚动摘要和最近整轮对话。
    compactor = ContextCompactor()
    msgs = [
        {
            "role": "system",
            "content": "You are a file and shell assistant. Workspace: "
            + ROOT
            + ". Handle files carefully. Reply in the user's language. "
            "run_cmd and run_powershell execute with the current user's permissions and are not confined to the workspace. "
            "You must not modify or delete files outside the workspace, or use shell commands to bypass file-tool path checks. "
            "Prefer file tools for file edits to preserve encoding.",
        }
    ]
    context_path = getattr(config, "CONTEXT_FILE", os.path.join(ROOT, ".win7harness-context.json"))
    try:
        msgs = load_context(context_path, msgs[0], compactor)
    except (OSError, ValueError) as e:
        raise SystemExit("Cannot load context %s: %s" % (context_path, e))
    max_tool_calls = getattr(config, "MAX_TOOL_CALLS", 999)
    if type(max_tool_calls) is not int or max_tool_calls < 1:
        raise ValueError("MAX_TOOL_CALLS must be a positive integer")
    print("Workspace:", ROOT)
    if len(msgs) > 1:
        print("[Context loaded]", context_path)
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
            save_context(context_path, msgs, compactor)
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
        save_context(context_path, msgs, compactor)
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
                    save_context(context_path, msgs, compactor)
                if api.STOP:
                    break
                print("\nAssistant> ", end="", flush=True)
                _, tcs = api.stream(msgs)
                print()
                if api.STOP or not tcs:
                    if not api.STOP:
                        save_context(context_path, msgs, compactor)
                    break

                for tc in tcs:
                    if api.check_control():
                        break
                    n = tc["function"]["name"]
                    action_no += 1
                    if action_no > max_tool_calls:
                        res = "Tool call limit reached"
                        show_action(action_no, n, {})
                        show_result(n, res)
                        msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": res})
                        continue

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
                save_context(context_path, msgs, compactor)
                if action_no >= max_tool_calls:
                    print("[Tool call limit reached]")
                    break

            if api.STOP:
                del msgs[snap:]
                save_context(context_path, msgs, compactor)
                print("[Turn discarded]")
                api.STOP = False
            if api.EXIT:
                break
        except KeyboardInterrupt:
            del msgs[snap:]
            save_context(context_path, msgs, compactor)
            api.STOP = False
            print("\n[Interrupted; turn discarded]")
        except Exception as e:
            del msgs[snap:]
            save_context(context_path, msgs, compactor)
            api.STOP = False
            print("\n[Error]", e)

    print("Bye")
