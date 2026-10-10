# -*- coding: utf-8 -*-
"""公共配置：API、模型、工作目录和操作限制。"""
import os

# API 请求地址；访问密钥在下一行 KEY 中设置。
API="https://api.deepseek.com/chat/completions"
KEY=""  # 填写本地 API 密钥；不要提交含密钥的 config.py。
# 以配置文件所在目录作为工作区。
ROOT=os.path.dirname(os.path.abspath(__file__))
# 保留机房实际验证可用的 API 模型名。
MODEL="deepseek-v4-flash"
# 其他工具结果的字符上限；读取文件不受此限制。
MAX_CHARS=8000
# 单轮任务允许的写操作尝试次数，包括修改和删除。
MAX_WRITES=10
# Esc 用于叫停当前轮次。
STOP_KEY=b'\x1b'
# 连续失败达到阈值后熔断，冷却时间单位为秒。
THRESH=5
COOL=60
