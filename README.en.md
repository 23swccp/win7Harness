# Win7 Harness

![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%207%20SP1%2B-0078D6?logo=windows)
![Dependencies](https://img.shields.io/badge/deps-requests%20only-blue)
![License](https://img.shields.io/badge/License-MIT-green)

[中文](README.md)

A lightweight command-line AI assistant for Windows 7, built with Python 3.8. It supports file operations, command execution, and context compaction.

The computers in my school's lab are awful: Windows 7, pip is all we get, and SSL/certificate problems prevent browser sign-ins.
Meanwhile, our teacher still expects us to write C# by hand.

- **Python 3.8 is enough** — the last CPython release series to officially support Windows 7.
- **No third-party libraries other than `requests`.**
- **Single-file deployment** — `harness_single.py` (about 46 KB).

## Requirements

| Item | Requirement |
| --- | --- |
| Operating system | Windows 7 SP1 or later, including Windows 10 / 11 |
| Python | 3.8+; Windows 7 is limited to Python 3.8 |
| Third-party dependency | `requests`; automatically installed at startup if missing or incompatible |
| Network | Access to your chosen API endpoint; a pip package index is also needed when installing dependencies for the first time |
| Command tools | `cmd.exe`; `run_powershell` uses syntax compatible with the built-in Windows PowerShell 2.0 |

## Quick Start

Copy `harness_single.py` into the workspace folder on the target machine, then run it in CMD:

```bat
python harness_single.py
```

On first run, enter the API URL, API key, and model name when prompted. To avoid entering them each time, fill in these three settings in the **configuration section** at the top of the file, which is generated from `config.example.py`.

The agent must only modify files inside the workspace.

## License and Acknowledgments

This project is licensed under the [MIT License](LICENSE).

OpenCode is my favorite harness.

The summary template and rolling-update prompts used for context compaction are adapted from [OpenCode](https://github.com/anomalyco/opencode) (MIT License, Copyright (c) 2025 opencode). The original copyright and license notice are retained in `context_compaction.py` and the generated single-file version.
