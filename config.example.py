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
