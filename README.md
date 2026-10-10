# Win7 文件助手

面向已有 Python 3.8 和 requests 的 Windows 7 环境。

首次取得源码时，将 config.example.py 复制为 config.py，填写 API 密钥，然后运行：

```bat
python harness.py
```

模型名保留 deepseek-v4-flash。config.py 是本地配置，不进入 Git；配置模板保存在 config.example.py。

支持文件读写、名称查找、文字搜索和终端动作显示。/quit 停止当前任务，/exit 退出，Esc 也可停止；停止不撤销已完成的文件修改。

注释使用中文，固定运行提示使用英文。会话不按消息条数或工具循环次数截断；读取文件不受 8000 字符限制，其他工具结果仍使用该上限。
