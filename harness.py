# -*- coding: utf-8 -*-
"""启动入口：在命令行运行 python harness.py。"""

import sys
import config
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
    from chat import main
    main()
