# Win7 Harness

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%207%20SP1%2B-0078D6?logo=windows)
![Dependencies](https://img.shields.io/badge/deps-requests%20only-blue)
![License](https://img.shields.io/badge/License-MIT-green)

[中文](README.md) | [English](README.en.md)

面向 Windows 7 的轻量命令行 AI 助手，使用 Python 3.8，支持文件操作、命令执行和上下文压缩。

在学校的垃圾机房电脑:win7系统,只能pip,SSL过期,证书限制无法登录浏览器
而老师却让我们手写C#

- **只依赖 Python 3.8** —— CPython 最后一个支持 Windows 7 的版本
- **除 `requests` 外不使用任何第三方库** 
- **单文件部署** —— `harness_single.py`（约 46 KB）

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 7 SP1 及以上（含 Windows 10 / 11） |
| Python | 3.8+（Windows 7 上最高只能到 3.8） |
| 第三方依赖 | `requests`，缺失或版本不符时启动自动安装 |
| 网络 | 可访问所选 API 端点；首次安装依赖时需要 pip 源 |
| 命令工具 | `cmd.exe`；`run_powershell` 使用系统自带 Windows PowerShell 2.0 兼容语法 |

## 快速开始
把 `harness_single.py` 复制到工作区文件夹，然后在cmd运行：

```bat
python harness_single.py
```

首次运行会提示输入 API URL、API key和模型名。想免去每次输入，就编辑文件开头的**配置区**（由 `config.example.py` 生成）填好这三项。
Agent只能修改工作区的文件.

## 许可与致谢
本项目采用 [MIT 许可证](LICENSE)。

opencode是我最喜欢的Harness

上下文压缩的摘要模板与滚动更新提示词移植自 [OpenCode](https://github.com/anomalyco/opencode)（MIT License，Copyright (c) 2025 opencode），原版权与许可声明保留在 `context_compaction.py` 及生成的单文件版中。



