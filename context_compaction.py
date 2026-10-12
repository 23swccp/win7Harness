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
import config
import api_client as api
from file_tools import TOOLS

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
