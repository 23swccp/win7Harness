# Win7 文件助手

面向已有 Python 3.8 的 Windows 7 环境，启动时自动检查并补装 requests。全程使用标准库(除了requests)编写,尤其注重代码的简洁,保证功能完善和可读性的前提下,代码的堆砌能少即少

首次取得源码时，将 config.example.py 复制为 config.py，然后运行：

```bat
python harness.py
```

工作区是启动时所在的目录。要操作其他目录，先进入该目录，再通过绝对路径运行 harness.py，例如在 `D:\项目A` 中运行 `python C:\工具目录\harness.py`，工作区就是 `D:\项目A`。配置仍从工具目录的 config.py 加载。

harness.py 启动时先检查 Python 至少为 3.8、requests 能导入且版本满足 `>=2.32.4,<3`。requests 缺失或版本不合格时，使用当前 Python 解释器的 pip 安装兼容版本；pip 缺失时先运行 ensurepip。安装后再次检查，失败则提示并退出，已有合格版本时直接启动。首次安装依赖需要网络，不需要 CMD 启动器或工具目录的 PATH 设置。

单文件版为 harness_single.py，只需复制这一个文件到目标电脑，运行 `python harness_single.py`（也可通过绝对路径启动）。它包含所有工具、聊天与压缩代码及配置模板，不依赖项目其他文件；API、KEY 等缺失配置会在启动时输入，也可修改文件开头的配置区。工作区同样是启动时所在目录，依赖自动检查和安装方式与分文件版一致。修改分文件源码后运行 `python build_single.py` 重新生成单文件版；生成时使用 config.example.py，不读取含本地配置的 config.py。

config.py 是本地配置，不进入 Git；配置模板保存在 config.example.py。API（URL）、KEY（API key）、MODEL（模型名）齐全时直接进入对话；留空或缺失的项会提示输入，API key 隐藏输入。补填只用于本次会话，不写回配置；如需下次直接进入，可在 config.py 中填写这三项。空值请写成 ""，不要写成 API= 这样的空赋值。

支持文件读写、名称查找、文字搜索和终端动作显示。/quit 停止当前任务，/exit 退出，Esc 也可停止；停止不撤销已完成的文件修改。

上下文压缩单独放在 context_compaction.py，摘要模板和滚动更新提示词移植自 [OpenCode](https://github.com/anomalyco/opencode/blob/773d8621d6bcd311067b225d837c917b3e83573e/packages/core/src/session/compaction.ts)，文件内保留上游 MIT 声明。默认 CONTEXT_TOKENS=128000（须不大于实际模型容量），预留回复空间后自动压缩；KEEP_TOKENS=15000，保留最近整轮消息和当前任务，工具调用与结果不拆开；SUMMARY_TOKENS=4096 控制摘要输出。旧 config.py 缺少这些选项时使用上述默认值。/compact 可手动压缩，CONTEXT_TOKENS=0 关闭自动压缩。摘要使用当前 API 和模型，但不提供工具；成功且确实缩短上下文后才替换历史，失败或中断保持原历史，同一任务内失败后不重复自动尝试。token 数按 UTF-8 字节粗估，不依赖额外 tokenizer；摘要有损且会额外消耗模型调用费用。

命令执行提供 run_cmd（CMD 语法）和 run_powershell（Windows PowerShell 2.0 兼容语法）。参数为 command、可选 cwd（默认工作区）、timeout（默认 60 秒）和 encoding（输出编码）。CMD 输出默认按系统 OEM 代码页解码，PowerShell 默认输出 UTF-8；外部程序使用其他编码时可指定 encoding。返回完成状态、退出码以及合并的标准输出和错误输出；超时或停止时结束命令进程树。每次调用启动新进程，变量和工作目录修改不跨调用保留。两种命令均计入 MAX_WRITES；cwd 限制在工作区，但命令本身以当前用户权限执行，不受文件工具的路径检查约束。需要保留文件编码时优先使用文件工具。

注释使用中文，固定运行提示使用英文。会话不按消息条数或工具循环次数截断；其他工具结果最多返回 MAX_CHARS（默认 8000）个字符。read_file 默认按字符分段读取，另附续读提示，支持从 0 开始的字符 offset；例如 offset=8000 读取下一段，大文件按段读取，不一次全部载入内存。

read_file 也可指定从 1 开始的 start_line、end_line（含首尾行），例如 start_line=20、end_line=40 读取第 20–40 行，返回每行带有 `20: 内容` 这样的行号前缀。按行读取每次在 MAX_CHARS 预算内返回完整行（行号也计入），不会在行中间切断；超出预算时附上 `[More lines; continue with start_line=N]`，续读时保留相同 encoding 和 end_line。单行本身超过预算时会报出其原文字符 offset，改用 offset 模式分段读取。未指定 start_line 时从第 1 行开始，未指定 end_line 时按预算逐页读到文件结束。行范围不能与 offset 同时使用；默认读取和 offset 续读仍返回原文。行号前缀不是文件内容，写入或替换时应去掉。

文字搜索、读取、覆盖、追加和替换均支持 encoding 参数，默认 UTF-8。GBK 文件指定 encoding="gbk"；Windows 本地 ANSI 编码可指定 "mbcs"。读取与后续修改需使用同一编码；解码失败会报错或在搜索结果中提示跳过，不用 U+FFFD 替代原内容。覆盖和追加先验证原文件可按指定编码解码、新内容可编码，失败时原文件不变；UTF-8 BOM 会保留，文件读写不自动转换换行符。

项目采用 [MIT 许可证](LICENSE)。OpenCode 摘要提示词的原版权与 MIT 声明保留在 context_compaction.py 和生成的单文件版中。
